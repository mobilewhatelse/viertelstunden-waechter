"""Decision engine of the quarter-hour peak guard.

Pure Python without Home Assistant imports, so it can be unit-tested and simulated offline.
The Home Assistant side (coordinator.py) reads the entity states into `Reading` objects, calls
`Guard.step()` every few seconds and executes (or, in observe mode, only logs) the returned actions.

Budget per quarter hour (what grid operators bill under a power-based tariff):
    E        energy imported so far in the running quarter hour (counter, cross-checked by integration)
    allowed  = (target * 0.25 h - E) / remaining time    average power that still fits until :15/:30/:45/:00
    excess   = import now - allowed
Short peaks are fine as long as the quarter-hour average stays below the target.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any

try:
    from .messages import Messages
except ImportError:  # loaded as a plain module (tests, simulation)
    from messages import Messages

V1 = 230.0
V3 = 3 * 230.0

KIND_WALLBOX = "wallbox"
KIND_EVCC = "evcc"          # a wallbox behind evcc: the guard sets evcc's ceiling of the loadpoint, otherwise a wallbox
WALLBOX_KINDS = (KIND_WALLBOX, KIND_EVCC)
KIND_SWITCH = "switch"
KIND_SCRIPT = "script"
KIND_BATTERY = "battery"
KIND_SETTING = "setting"    # changes settings (e.g. block contact of a heat pump) and puts them back
KIND_VEHICLE = "vehicle"    # charge plan for a car: not an actuator of the guard
KIND_THROTTLE = "throttle"  # lowers a number (percent, watts, amps) stepwise and gives it back stepwise
SETTING_KINDS = (KIND_BATTERY, KIND_SETTING)
GUARDED_KINDS = (KIND_BATTERY, KIND_SETTING, KIND_THROTTLE)

STRATEGY_COMFORT = "comfort"  # least loss of comfort: cheapest combination of devices that is enough
STRATEGY_ORDER = "order"      # strict order by priority, like a fixed list

SETTLE_S = 40                 # after a change, give devices time to react before the next step
WALLBOX_STEP_S = 40
PHASE_PAUSE_S = 120           # a phase switch interrupts charging; some chargers even report "complete" meanwhile
TO_ONE_PHASE_AFTER_S = 120    # go 1-phase only if 3-phase minimum has not been enough for this long (cookers cycle)
TO_THREE_PHASE_AFTER_S = 300  # back to 3-phase only after this long with enough headroom
RELEASE_EVERY_S = 60
ROOM_SUSTAIN_S = 120          # give back only if the headroom held this long (cookers and kettles cycle)
MIN_OFF_S = 300               # a switched-off device stays off at least this long (no flapping)
FAST_AVG_S = 60
STEP_TOLERANCE_S = 25        # one cycle of slack when checking how long something held
WALLBOX_UP_AFTER_S = 90
MISSING_DATA_S = 90           # no grid reading this long: give everything back
VERIFY_S = 60                # an intervention must show in the readings after this long, else it is repeated once
MISS_REST_MIN = 10            # a device that did not follow is left alone this long, the next lever is used
VERIFY_MAX_S = 300            # a device whose power sensor reports rarely (cloud) is checked after at most this long
POWER_GAP_KEEP = 6            # gaps between new power values remembered per device
POWER_GAP_MIN_KW = 0.3        # gaps count only while the device draws at least this much
POWER_GAP_MIN_N = 3           # gaps needed before the measured interval is used
MAX_PLAUSIBLE_KW = 60.0       # counter jumps after an outage are not real peaks (without a limit; see plausible_kw)
MIN_PLAUSIBLE_KW = 25.0       # ... and never tighter than this (a house connection of 3 x 35 A)
PLAUSIBLE_LIMITS = 4.0        # an average of more than this many times the own limit is no measurement
COUNTER_SILENT_S = 1200.0     # a counter that said nothing for longer than a quarter hour and then steps: the step is the backlog
COUNTER_JUMP_KWH = 0.1        # ... if it is this much more than (half as much again as) the power sensor measured in the
COUNTER_JUMP_FACTOR = 1.5     #     running quarter hour (a counter that reports every quarter hour is never meant)
COUNTER_GAP_KEEP = 15         # gaps between new counter values remembered (the usual interval of the counter, as power_gap)
COUNTER_GAP_FACTOR = 2.5      # a gap counts as an outage only if it is this much longer than the usual interval (a cloud counter
                              # that reports every 20 to 30 minutes is no outage, review 20.11.2026)
# precautionary lock (0.15.1, issue #5): a device that is not running is kept locked while its start would not fit
PC_KINDS = (KIND_SETTING,)    # extension point: other kinds (switch: keep off; throttle: keep low) need their own lock/release
PC_MAX_MIN = 30.0             # a precautionary lock never lasts longer than this (default of the device setting)
PC_GAP_MIN = 3.0              # at least this long between two changes of the same device (lock, release; compressor protection)
PC_HYST_KW = 0.2              # released only with this much more headroom than the start needs (no flapping at the border)
PC_VERIFY_S = 90              # a lock that does not show in the readings after this long is given up (setting did not change)
PC_DAY_H = 4.0                # at most this many hours of precautionary lock per calendar day and device (0 = no daily limit)
PC_OBSERVED = "~beobachtet"   # key suffix of the daily sum of locks that were only observed (not stored, never limits real ones)
# wallbox may pause as the last measure (0.16.0, BETA, device switch "may_pause", default off): only at the minimum current, with every
# other lever used up, and only after this has lasted PAUSE_AFTER_S. Minimum duration of the pause and the pause after taking back
# before the next one are the device fields hold_min / pause_min (0 = MIN_OFF_S), as at the switchable devices
PAUSE_AFTER_S = 120           # at the minimum and still too much this long (like the wait before 1 phase: cookers cycle)
PAUSE_MARGIN_KW = 0.5         # allowed again only with room for the minimum current plus this
PAUSE_USER_REST_MIN = 60      # someone changed the mode during a pause: no new pause of this wallbox for this long
RESUME_WAIT_S = 180           # after allowing again the car needs a while to start: meanwhile it counts as charging (current stays)


def plausible_kw(limit_kw: float | None) -> float:
    """The highest quarter-hour average a counter step may mean: four times the own limit, at least 25 kW (issue #4: 60 kW
    for every house let the backlog of hours through)."""
    if not limit_kw or limit_kw <= 0:
        return MAX_PLAUSIBLE_KW
    return max(MIN_PLAUSIBLE_KW, PLAUSIBLE_LIMITS * float(limit_kw))
CHARGING_W = 500.0


@dataclass
class DeviceConfig:
    """What the guard may do with one device."""

    id: str
    name: str
    kind: str
    priority: int = 5             # 1 = restricted first (least important), 10 = only in an emergency
    min_power_w: float = 100.0    # switch: counts as running only above this
    power_w: float = 0.0          # switch without power sensor / script: assumed reduction in W
    max_off_min: float = 0.0      # switch/script: never longer than this (0 = no limit)
    min_current: int = 6          # wallbox
    max_current: int = 16
    one_phase_option: str | None = None  # wallbox: select option for 1 phase; None = no phase switching
    min_soc: float = 30.0         # battery: only released at or above this state of charge (%); setting/throttle: comfort minimum
    min_value: float = 0.0        # throttle: never lower than this
    max_value: float = 100.0      # throttle: normal value
    step: float = 5.0             # throttle: step size
    hold_min: float = 0.0         # minimum time an intervention is kept (0 = general default of 5 minutes)
    pause_min: float = 0.0        # minimum pause after taking back before the next intervention (compressor protection)
    observe_only: bool = False    # only say what would be done with it; never a lever, nothing is sent
    start_kw: float = 0.0         # precautionary lock (draft): power at the start in kW; 0 = off (the behaviour of before)
    start_max_min: float = PC_MAX_MIN  # ... never locked longer than this
    start_gap_min: float = PC_GAP_MIN  # ... at least this long between two of its changes
    start_day_h: float = PC_DAY_H      # ... at most this many hours locked per calendar day (0 = no daily limit)
    may_pause: bool = False       # wallbox (0.16.0, BETA): may be paused as the last measure (needs a way to pause and allow again)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeviceConfig:
        return cls(
            id=str(d["id"]),
            name=str(d.get("name") or d["id"]),
            kind=str(d["kind"]),
            priority=int(d.get("priority", 5)),
            min_power_w=float(d.get("min_power_w", 100.0)),
            power_w=float(d.get("power_w", 0.0)),
            max_off_min=float(d.get("max_off_min", 0.0)),
            min_current=int(d.get("min_current", 6)),
            max_current=int(d.get("max_current", 16)),
            one_phase_option=d.get("one_phase_option") or None,
            min_soc=float(d.get("min_soc", d.get("comfort_min", 30.0 if d.get("kind") == "battery" else 0.0))),
            min_value=float(d.get("min_value", 0.0)),
            max_value=float(d.get("max_value", 100.0)),
            step=max(0.001, float(d.get("step", 5.0))),
            hold_min=float(d.get("hold_min", 0.0)),
            pause_min=float(d.get("pause_min", 0.0)),
            observe_only=bool(d.get("observe_only", False)),
            start_kw=max(0.0, float(d.get("start_kw") or 0.0)),
            start_max_min=max(1.0, float(d.get("start_max_min") or PC_MAX_MIN)),
            start_gap_min=max(0.0, float(d.get("start_gap_min", PC_GAP_MIN) or 0.0)),
            start_day_h=min(24.0, max(0.0, float(PC_DAY_H if d.get("start_day_h") is None else d["start_day_h"]))),
            may_pause=bool(d.get("may_pause", False)),
        )


@dataclass
class Reading:
    """State of one device in this cycle."""

    available: bool = True
    power_w: float | None = None
    is_on: bool | None = None
    current_a: float | None = None
    phase_option: str | None = None
    phases: int | None = None
    allowed: bool = True          # condition entity: an intervention is possible right now
    restore_allowed: bool = True  # switch: may be switched back on (e.g. still within its schedule)
    soc: float | None = None      # battery: state of charge in %
    releasable: bool = True       # battery/setting: at least one setting differs from its release value
    value: float | None = None    # throttle: current value of the number
    current_steps: tuple[int, ...] | None = None  # wallbox with a list of currents (select): the amps it offers, else any whole amp
    power_gap_s: float | None = None  # typical seconds between new values of the power sensor (None: not measured yet)
    running: bool | None = None   # precautionary lock: the "running" entity of the device (None = none, the power decides)
    mode: str | None = None       # wallbox behind evcc: the mode of the loadpoint (remembered when the guard pauses it)
    paused: bool | None = None    # wallbox: it is paused now (evcc mode off, the pause command shows); None = cannot tell


def power_gap(gaps: list[float]) -> float | None:
    """Median of the measured gaps between new power values, or None while fewer than POWER_GAP_MIN_N are known."""
    if len(gaps) < POWER_GAP_MIN_N:
        return None
    s = sorted(gaps)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


FORECAST_SMOOTH_S = 120.0     # display option: in the first two minutes of a quarter hour the forecast leans on the typical value


def smoothed_forecast(raw_kw: float | None, typical_kw: float | None, elapsed_s: float) -> float | None:
    """Only for the display (option *smooth the forecast at the quarter start*, 0.15.1): right after a quarter hour began the
    projection is nearly the power of this moment (a kettle shows as a quarter hour of 10 kW). In the first FORECAST_SMOOTH_S it
    is mixed with the typical value of this quarter hour, the weight moving linearly to the measurement. The control never
    uses this value."""
    if raw_kw is None or typical_kw is None or elapsed_s >= FORECAST_SMOOTH_S:
        return raw_kw
    w = max(0.0, elapsed_s) / FORECAST_SMOOTH_S
    return round(w * raw_kw + (1.0 - w) * float(typical_kw), 2)


def verify_wait(r: Reading | None) -> float:
    """Seconds after a command before the readings must show it: the usual minute, longer for a power sensor
    that reports rarely (one and a half of its intervals plus a cycle), never more than VERIFY_MAX_S."""
    gap = r.power_gap_s if r is not None else None
    if not gap:
        return float(VERIFY_S)
    return min(float(VERIFY_MAX_S), max(float(VERIFY_S), gap * 1.5 + 20.0))


@dataclass
class Action:
    device_id: str
    kind: str                     # set_current, set_phase, turn_off, turn_on, script_on, script_off, notify, log
    value: Any = None
    text: str = ""
    intervention: bool = True     # counts as an intervention (reduction), not as a release


@dataclass
class _Option:
    device: DeviceConfig
    reduction_kw: float


def _secs(t: datetime | None, now: datetime) -> float:
    return 1e9 if t is None else (now - t).total_seconds()


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def amps_of(option: Any) -> int | None:
    """The current in a list entry of a wallbox: '8 A', '8A', '8', '8,0 A' -> 8; with phases in front ('3x16 A', '1 x 16 A',
    '3×16A') the current after the x, not the phase count; None when there is no number."""
    s = str(option)
    m = _PHASES_X_AMPS.search(s) or re.search(r"(\d+(?:[.,]\d+)?)", s)
    return int(float(m.group(m.lastindex or 0).replace(",", "."))) if m else None


_PHASES_X_AMPS = re.compile(r"\b([123])\s*[xX×*]\s*(\d+(?:[.,]\d+)?)")


def phases_of(option: Any) -> int | None:
    """The phase count written in a list entry ('3x16 A' -> 3, '1x16 A' -> 1); None without one ('16 A')."""
    m = _PHASES_X_AMPS.search(str(option))
    return int(m.group(1)) if m else None


def pick_option(options: list[Any], amps: int, current: Any = None) -> Any:
    """The list entry with `amps`; with entries for one and three phases ('1x16 A', '3x16 A') the one with the phase count of
    the present entry, so lowering the current never switches the phases. None if there is no entry with these amps."""
    hits = [o for o in options if amps_of(o) == amps]
    same = [o for o in hits if phases_of(o) == phases_of(current)]
    return (same or hits or [None])[0]


def percent_of(value: Any) -> float | None:
    """A target state of charge: '80', '80.0', '80%', '80 %', '80,5' -> the number; None outside 1..100 or without a number
    ('Unsupported' of Fordpass when the car has no target)."""
    try:
        val = float(str(value).replace("%", "").strip().replace(",", "."))
    except ValueError:
        return None
    return val if 0 < val <= 100 else None


def step_down(amps: int, steps: tuple[int, ...] | None) -> int:
    """The highest current the wallbox offers that is not above `amps` (never more than wanted); below its lowest one the lowest.
    Without a list (a number entity) every whole amp is possible."""
    if not steps:
        return amps
    below = [s for s in steps if s <= amps]
    return max(below) if below else min(steps)


class Guard:
    """Keeps the quarter-hour average of the grid import below a target."""

    def __init__(self, devices: list[DeviceConfig], strategy: str = STRATEGY_COMFORT, voltage: float = V1,
                 lang: str = "de") -> None:
        self.t = Messages(lang)           # texts of the log lines in the language of Home Assistant
        self._watch_noted: set[tuple[str, Any]] = set()  # (device, quarter) already noted for observe-only devices
        self.v1 = float(voltage)          # voltage of one phase (230 V in Europe)
        self.v3 = 3.0 * float(voltage)    # three phases
        self.devices: dict[str, DeviceConfig] = {d.id: d for d in devices}
        self.strategy = strategy
        self.interventions: dict[str, dict[str, Any]] = {}
        self.quarter: datetime | None = None
        self.energy_kwh = 0.0
        self.quarter_estimated = False     # the running quarter hour began with a guess (started in its middle, nothing to resume)
        self.finished_estimated = False    # ... and so did the quarter hour that just ended: its value is no measurement
        self._resume: dict[str, Any] | None = None
        self.finished_quarter_kw: float | None = None  # set in the cycle in which a quarter hour ended
        self.values: dict[str, Any] = {}
        self.state = "ready"
        self._counter_at_q: float | None = None
        self._counter_seen: float | None = None        # the last counter value and when it last changed: a counter that
        self._counter_changed: datetime | None = None  # stood still and then steps brings the backlog of the whole gap
        self._counter_gaps: list[float] = []           # seconds between the last new counter values (its usual interval)
        self._power_hole = False                       # the power sensor had no value since the counter last changed
        self.max_plausible_kw = MAX_PLAUSIBLE_KW       # set from the limit in step()
        self._last_t: datetime | None = None
        self._last_p = 0.0
        self._last_action: datetime | None = None
        self._last_release: datetime | None = None
        self._wb: dict[str, dict[str, datetime | None]] = {}
        self._rest_until: dict[str, datetime] = {}
        self._notified_q: datetime | None = None
        self._missing_since: datetime | None = None
        self._p_hist: list[tuple[datetime, float]] = []
        self.real_effect = True            # False in observe mode: nothing was really changed, so nothing was saved
        self.saved_kwh = 0.0               # estimated energy the interventions kept out of this quarter hour
        self.finished_unguarded_kw: float | None = None  # estimated average without the guard, set when a quarter ends
        self._last_saved = 0.0
        self._restored: dict[str, datetime] = {}
        self._pending: dict[str, dict[str, Any]] = {}  # interventions waiting for their confirmation
        self._smooth = False               # forecast-based step: no phase switching
        self.misses = 0                    # interventions that never showed in the readings (since start)
        self._now = datetime.min
        # precautionary lock (0.15.1): kept apart from `interventions`, so the release order of the normal control is untouched
        self.precaution: dict[str, dict[str, Any]] = {}   # device -> {"since", "room", "shadow"} while the guard holds it locked
        self._pc_last: dict[str, datetime] = {}           # last change of the device by the guard (lock or release, both logics)
        self._pc_rest: dict[str, datetime] = {}           # no new precautionary lock before this (after the maximum time)
        self._pc_noted: set[str] = set()                  # notes said once per device (no sensor to tell whether it runs)
        self._pc_ok: dict[str, datetime] = {}             # since when the headroom for the start holds (release after 120 s)
        # daily limit: key -> {"day": "YYYY-MM-DD", "s": seconds locked that day, "noted": bool}; the real ones survive a restart
        self._pc_day: dict[str, dict[str, Any]] = {}
        self._pc_at: dict[str, datetime] = {}             # when the daily sum was last counted up (only while locked)
        self._pause_rest: dict[str, datetime] = {}        # wallbox pause (0.16.0): no new pause of the device before this

    # ---------- persistence ----------

    def day_state(self) -> dict[str, Any]:
        """The daily sums of the precautionary locks that were really carried out (empty without any): saved like the marker."""
        return {k: dict(v) for k, v in self._pc_day.items() if not k.endswith(PC_OBSERVED) and v.get("s")}

    def load_day(self, d: Any) -> None:
        """The daily sums from before a restart (a sum of another day is reset by the first count of the new day)."""
        if not isinstance(d, dict):
            return
        for k, v in d.items():
            if k in self.devices and isinstance(v, dict) and isinstance(v.get("day"), str):
                try:
                    self._pc_day[k] = {"day": v["day"], "s": max(0.0, float(v.get("s") or 0.0)), "noted": bool(v.get("noted"))}
                except (TypeError, ValueError):
                    continue

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"interventions": self.interventions}
        if self.precaution:
            out["precaution"] = self.precaution
        return out

    def load(self, d: dict[str, Any]) -> None:
        self.interventions = {k: v for k, v in (d.get("interventions") or {}).items() if k in self.devices}
        # a precautionary lock from before a restart: only to be given back by release_all (never continued)
        self.precaution = {k: v for k, v in (d.get("precaution") or {}).items()
                           if k in self.devices and isinstance(v, dict) and not v.get("shadow")}

    # ---------- quarter-hour accounting ----------

    def quarter_state(self) -> dict[str, Any] | None:
        """The running quarter hour, to be saved when the guard stops (a reload, a restart of Home Assistant)."""
        if self.quarter is None:
            return None
        return {"quarter": self.quarter.isoformat(), "energy_kwh": round(self.energy_kwh, 4), "saved_kwh": round(self.saved_kwh, 4),
                "counter_at_q": self._counter_at_q, "at": self._last_t.isoformat() if self._last_t else None,
                "estimated": self.quarter_estimated}

    def resume_quarter(self, state: dict[str, Any] | None) -> None:
        """What was saved at the last stop; used by the first cycle if it is still the same quarter hour."""
        self._resume = state if isinstance(state, dict) else None

    def _resume_into(self, q: datetime, now: datetime, grid_kw: float | None, counter_kwh: float | None) -> bool:
        """Continue the quarter hour that was running when the guard stopped: with the counter exactly (it also counted while the
        guard was away), else the saved energy plus the gap at the present power. False if there is nothing to continue."""
        r, self._resume = self._resume, None
        if not r or r.get("quarter") != q.isoformat():
            return False
        try:
            saved_energy, at = float(r.get("energy_kwh") or 0.0), datetime.fromisoformat(str(r.get("at")))
        except (TypeError, ValueError):
            return False
        elapsed_h = max(1.0, (now - q).total_seconds()) / 3600.0
        base = r.get("counter_at_q")
        if counter_kwh is not None and base is not None and 0.0 <= counter_kwh - float(base) <= self.max_plausible_kw * elapsed_h + 0.05:
            self.energy_kwh = counter_kwh - float(base)
        else:
            gap_h = max(0.0, min((now - q).total_seconds(), (now - at).total_seconds())) / 3600.0
            self.energy_kwh = saved_energy + (grid_kw or 0.0) * gap_h
        self.saved_kwh = float(r.get("saved_kwh") or 0.0)
        self.quarter_estimated = bool(r.get("estimated"))
        return True

    def _account(self, now: datetime, grid_kw: float | None, counter_kwh: float | None) -> None:
        self.finished_quarter_kw = None
        self.finished_unguarded_kw = None
        self.finished_estimated = False
        q = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        if self.quarter != q:
            first = self.quarter is None
            if not first and self.quarter == q - timedelta(minutes=15):
                if self._last_t is not None:
                    tail = max(0.0, min(60.0, (q - self._last_t).total_seconds())) / 3600.0
                    self.energy_kwh += self._last_p * tail
                    self.saved_kwh += self._last_saved * tail
                self.finished_quarter_kw = round(self.energy_kwh / 0.25, 3)
                self.finished_unguarded_kw = round((self.energy_kwh + self.saved_kwh) / 0.25, 3)
                self.finished_estimated = self.quarter_estimated
            self.quarter = q
            self.energy_kwh = 0.0
            self.saved_kwh = 0.0
            self.quarter_estimated = False
            self._notified_q = None
            if first:
                if not self._resume_into(q, now, grid_kw, counter_kwh):
                    # started in the middle of a quarter hour with nothing to continue: guess what came before from the present
                    # power. Careful for the control, but no measurement: this quarter hour is not recorded as a peak.
                    self.energy_kwh = (grid_kw or 0.0) * (now - q).total_seconds() / 3600.0
                    self.quarter_estimated = (now - q).total_seconds() > 30.0
                self._last_t = now
            else:
                self._last_t = q
            self._counter_at_q = counter_kwh - self.energy_kwh if counter_kwh is not None else None
        if grid_kw is not None and self._last_t is not None:
            dt = max(0.0, min(60.0, (now - self._last_t).total_seconds()))
            self.energy_kwh += self._last_p * dt / 3600.0
            self.saved_kwh += self._last_saved * dt / 3600.0
        if grid_kw is None:
            self._power_hole = True
        if counter_kwh is not None:
            if self._counter_at_q is None:
                self._counter_at_q = counter_kwh - self.energy_kwh
            self._counter_backlog(now, q, counter_kwh)
            diff = counter_kwh - self._counter_at_q
            elapsed_h = max(1.0, (now - q).total_seconds()) / 3600.0
            if 0.0 <= diff <= self.max_plausible_kw * elapsed_h + 0.05:
                self.energy_kwh = max(self.energy_kwh, diff)  # the counter is the better source; take the larger (careful)
        if grid_kw is not None:
            self._last_t, self._last_p = now, grid_kw

    def _counter_backlog(self, now: datetime, q: datetime, counter_kwh: float) -> None:
        """A counter that stood still for longer than a quarter hour (the meter or its connection was away) and then steps
        brings the energy of the whole gap at once. That is not the import of the running quarter hour (issue #4: no values
        from 02:00 to 06:15, then 5 kWh in one step, recorded as a peak of 20 kW). The step is left out, the quarter hour goes on
        with what the power sensor measured and counts as estimated: it is not recorded as a peak. A counter that only stood
        still because nothing was imported (the sun covered the house) steps by what the power sensor saw too: nothing happens.
        A counter that always reports rarely (a cloud counter every 20 to 30 minutes, review 20.11.2026) is no outage: the gap
        must be clearly longer than its usual interval (median of the last gaps, like power_gap); while that is not known yet,
        only a gap in which the power sensor had no value either counts. Such a normal step that began before the running quarter
        hour is shared by time: only the part after the quarter start belongs to it (the rest was the quarter hour before)."""
        seen, changed = self._counter_seen, self._counter_changed
        if seen is None or changed is None:
            self._counter_seen, self._counter_changed = counter_kwh, now
            self._power_hole = False
            return
        if counter_kwh == seen:
            return
        step = counter_kwh - seen
        silent = (now - changed).total_seconds()
        hole, self._power_hole = self._power_hole, False
        usual = power_gap(self._counter_gaps)
        self._counter_gaps = (self._counter_gaps + [silent])[-COUNTER_GAP_KEEP:]
        self._counter_seen, self._counter_changed = counter_kwh, now
        if changed >= q:
            return
        outage = silent >= COUNTER_SILENT_S and (silent >= COUNTER_GAP_FACTOR * usual if usual is not None else hole)
        if outage and step > COUNTER_JUMP_FACTOR * self.energy_kwh + COUNTER_JUMP_KWH:
            self._counter_at_q = counter_kwh - self.energy_kwh
            self.quarter_estimated = True
        elif step > 0.0 and silent > 0.0:
            share = max(0.0, min(1.0, (now - q).total_seconds() / silent))
            self._counter_at_q = counter_kwh - step * share

    # ---------- main step ----------

    def step(
        self,
        now: datetime,
        grid_kw: float | None,
        counter_kwh: float | None,
        readings: dict[str, Reading],
        limit_kw: float,
        margin_kw: float,
        enabled: bool,
        reserve_kw: float = 0.0,
        reserve_text: str = "",
    ) -> list[Action]:
        self._now = now
        self.max_plausible_kw = plausible_kw(limit_kw)
        self._account(now, grid_kw, counter_kwh)
        target = limit_kw - margin_kw
        q_end = self.quarter + timedelta(minutes=15)
        rest_h = max(1.0, (q_end - now).total_seconds()) / 3600.0
        p_now = grid_kw if grid_kw is not None else self._last_p
        # Cookers and kettles cycle on and off within seconds; the bill only sees the quarter-hour average.
        # Decide on averages: 60 s for cutting, 120 s (and only since the last change) for giving back.
        self._p_hist = [x for x in self._p_hist if _secs(x[0], now) <= ROOM_SUSTAIN_S] + [(now, p_now)]
        fast = [x[1] for x in self._p_hist if _secs(x[0], now) <= FAST_AVG_S]
        p = sum(fast) / len(fast)
        allowed = (target * 0.25 - self.energy_kwh) / rest_h
        forecast = (self.energy_kwh + p * rest_h) / 0.25
        excess = p - allowed
        if excess <= 0.1:   # the wait before a wallbox pause starts again (only set with a device that may pause)
            for t in self._wb.values():
                t.pop("pause_need", None)
        self.values = {
            "limit_kw": limit_kw,
            "target_kw": round(target, 2),
            "grid_kw": round(p, 3),
            "quarter_energy_kwh": round(self.energy_kwh, 3),
            "allowed_kw": round(allowed, 2),
            "forecast_kw": round(forecast, 2),
            "quarter": self.quarter,
            "reserve_kw": round(reserve_kw, 2),
        }
        self._last_saved = self._saved_kw(readings)
        self.values["saved_kw"] = round(self._last_saved, 2)
        self.values["unconfirmed"] = self.misses

        if grid_kw is None:
            if self._missing_since is None:
                self._missing_since = now
            if _secs(self._missing_since, now) >= MISSING_DATA_S:
                self.state = "no_data"
                return self.release_all(now, readings, self.t("r_missing"))
            return []
        self._missing_since = None

        if not enabled:
            self.state = "idle"
            return self.release_all(now, readings, self.t("r_not_needed")) if self.interventions or self.precaution else []

        # headroom that fits permanently (not the rest budget near :15): average of the last two minutes,
        # counted only since the last change, so a release is judged on the situation after the previous one
        changed = max([t for t in (self._last_action, self._last_release) if t is not None], default=None)
        slow = [x for x in self._p_hist if changed is None or x[0] > changed]
        held = bool(slow) and _secs(slow[0][0], now) >= ROOM_SUSTAIN_S - STEP_TOLERANCE_S
        room = min(allowed, target) - reserve_kw - sum(x[1] for x in slow) / len(slow) if held else -1.0
        self.values["room_kw"] = round(room, 2)

        checks = self._verify(now, readings)
        pause_notes = self._pause_watch_all(now, readings)   # 0.16.0: [] without a wallbox paused by the guard
        actions = pause_notes + self._forced_releases(now, readings)
        if excess > 0.1:
            actions = actions + self._watch_notes(now, readings, excess)
        if not [a for a in actions if a.kind != "log"]:
            if excess > 0.1:
                actions = actions + self._reduce(now, excess, readings, forecast, limit_kw, rest_h)
            elif reserve_kw > 0 and p - (allowed - reserve_kw) > 0.1:
                # forecast says a spike is usual in this quarter hour: take the smooth levers (wallbox, throttle) early
                self._smooth = True
                try:
                    actions = self._reduce(now, p - (allowed - reserve_kw), readings, forecast, limit_kw, rest_h,
                                           smooth_only=True)
                finally:
                    self._smooth = False
                for a in actions:
                    if a.text:
                        a.text = self.t("ahead", why=reserve_text, text=a.text)
                actions = pause_notes + actions
            else:
                if room > 0:  # only real, lasting headroom ends the wait for 1-phase (a cooker's off-phase does not)
                    for t in self._wb.values():
                        t["too_little"] = None
                actions = pause_notes + self._release(now, room, readings)
        self._register(now, readings, actions)
        self.state = "intervening" if self.interventions else "ready"
        if not any(d.start_kw > 0 for d in self.devices.values()) and not self.precaution:
            return checks + actions   # no device with a start power: exactly the behaviour of before
        pc = self._precaution_step(now, readings, min(allowed, target) - p, checks + actions)
        self.values["precaution"] = sorted(self.precaution)
        return checks + actions + pc

    # ---------- precautionary lock (0.15.1, issue #5) ----------

    def _pc_running(self, dev: DeviceConfig, r: Reading) -> bool | None:
        """Whether the device runs: its "running" entity if it has one, else its power against min_power_w; None = unknown."""
        if r.running is not None:
            return r.running
        if r.power_w is None:
            return None
        return r.power_w >= dev.min_power_w

    def _pc_lock(self, dev: DeviceConfig, room: float, now: datetime) -> Action:
        shadow = not self.real_effect or dev.observe_only
        self.precaution[dev.id] = {"since": now.isoformat(), "room": round(room, 2), "shadow": shadow}
        self._pc_last[dev.id] = now
        self._pc_at[self._pc_key(dev.id, shadow)] = now   # the daily sum counts from here
        text = self.t("pc_would_lock" if shadow else "pc_lock", name=dev.name, room=max(0.0, room), kw=dev.start_kw)
        # extension point: KIND_SETTING locks with the release values of its settings (the same command as the normal control,
        # so the value for "locked" is the one of the device setting); a switch would be "turn_off", a throttle "set_value"
        return Action(dev.id, "log" if shadow else "battery_release", None, text, False)

    @staticmethod
    def _pc_key(dev_id: str, shadow: bool) -> str:
        return dev_id + PC_OBSERVED if shadow else dev_id

    def _pc_today(self, dev_id: str, shadow: bool, now: datetime) -> dict[str, Any]:
        """The daily sum of this device for the calendar day of `now` (a sum of another day starts again at 0)."""
        key, day = self._pc_key(dev_id, shadow), now.strftime("%Y-%m-%d")
        b = self._pc_day.get(key)
        if b is None or b.get("day") != day:
            b = self._pc_day[key] = {"day": day, "s": 0.0, "noted": False}
        return b

    def _pc_count(self, dev_id: str, shadow: bool, now: datetime) -> dict[str, Any]:
        """Count the time locked since the last count into the sum of today (at most one minute per count: a gap in the cycles,
        e.g. Home Assistant was busy, is not counted as locked time). At midnight the new day begins with what came after it."""
        key = self._pc_key(dev_id, shadow)
        at = self._pc_at.get(key)
        if at is not None and at.date() != now.date():
            at = now.replace(hour=0, minute=0, second=0, microsecond=0)
        b = self._pc_today(dev_id, shadow, now)
        if at is not None:
            b["s"] += max(0.0, min(60.0, (now - at).total_seconds()))
        self._pc_at[key] = now
        return b

    def _pc_free(self, dev: DeviceConfig, now: datetime, text: str) -> Action:
        st = self.precaution.pop(dev.id, None) or {}
        self._pc_last[dev.id] = now
        self._pc_ok.pop(dev.id, None)
        if st:
            self._pc_count(dev.id, bool(st.get("shadow")), now)
            self._pc_at.pop(self._pc_key(dev.id, bool(st.get("shadow"))), None)
        if st.get("shadow"):
            return Action(dev.id, "log", None, text, False)
        # battery_restore puts back only the settings that still hold the release value (coordinator: _battery_restore), so a
        # lock of the utility (EVU) or of the user that came meanwhile is not lifted by the guard's own
        return Action(dev.id, "battery_restore", None, text, False)

    def _precaution_step(self, now: datetime, readings: dict[str, Reading], room: float, acts: list[Action]) -> list[Action]:
        """Keep a device that is not running locked while its start would not fit: `room` = min(allowed, target) - import.

        Safety nets: never a device that runs or that the normal control holds; never longer than start_max_min (then free and
        a pause of the same length); at least start_gap_min between two changes; given back by release_all (no data, not needed,
        mode changed, restart, integration stopped). In observe mode (or with observe only at the device) nothing is sent: the
        log says what would have been done, and when the device then starts, that the start would have been put off."""
        out: list[Action] = []
        touched = {a.device_id for a in acts if a.kind != "log"}
        for dev_id, dev in self.devices.items():
            if a := self._pc_device(dev, readings.get(dev_id), room, now, dev_id in touched):
                out.append(a)
        # a change of the normal control counts for the gap too (no lock right after it gave the device back)
        for a in acts:
            if a.kind in ("battery_release", "battery_restore") and a.device_id in self.devices and self.devices[a.device_id].start_kw > 0:
                self._pc_last[a.device_id] = now
        return out

    def _pc_device(self, dev: DeviceConfig, r: Reading | None, room: float, now: datetime, touched: bool) -> Action | None:
        st = self.precaution.get(dev.id)
        if st is not None:
            return self._pc_held(dev, r, st, room, now)
        if dev.kind not in PC_KINDS or dev.start_kw <= 0:
            return None
        if touched or dev.id in self.interventions or now < self._pc_rest.get(dev.id, now):
            return None
        if r is None or not r.available or not r.allowed or not r.releasable:
            return None   # not reachable, the condition entity says no, or already locked (by the utility, the user, the guard)
        if r.soc is not None and r.soc < dev.min_soc:
            return None   # the comfort value (room, hot water) is below its minimum: never kept from starting
        running = self._pc_running(dev, r)
        if running is None:
            if dev.id not in self._pc_noted:
                self._pc_noted.add(dev.id)
                return Action(dev.id, "log", None, self.t("pc_no_sensor", name=dev.name), False)
            return None
        if running or room >= dev.start_kw:
            return None
        if _secs(self._pc_last.get(dev.id), now) < dev.start_gap_min * 60:
            return None
        shadow = not self.real_effect or dev.observe_only
        if dev.start_day_h > 0 and self._pc_today(dev.id, shadow, now)["s"] >= dev.start_day_h * 3600:
            return None   # daily limit reached: no further precautionary lock until the next day (said once, when reached)
        return self._pc_lock(dev, room, now)

    def _pc_held(self, dev: DeviceConfig, r: Reading | None, st: dict[str, Any], room: float, now: datetime) -> Action | None:
        try:
            age = (now - datetime.fromisoformat(str(st.get("since")))).total_seconds()
        except (TypeError, ValueError):
            age = 1e9
        shadow = bool(st.get("shadow"))
        if dev.kind not in PC_KINDS or dev.start_kw <= 0:   # the field was set to 0 meanwhile
            return self._pc_free(dev, now, self.t("pc_off", name=dev.name))
        if age >= dev.start_max_min * 60:
            self._pc_rest[dev.id] = now + timedelta(minutes=dev.start_max_min)
            return self._pc_free(dev, now, self.t("pc_max", name=dev.name, min=dev.start_max_min))
        day = self._pc_count(dev.id, shadow, now)
        if dev.start_day_h > 0 and day["s"] >= dev.start_day_h * 3600:
            noted, day["noted"] = day["noted"], True
            act = self._pc_free(dev, now, self.t("pc_day", name=dev.name, h=dev.start_day_h))
            if noted:   # the note only once a day (e.g. reached again after a restart): freed all the same
                act.text = self.t("pc_back", name=dev.name)
            return act
        if dev.id in self.interventions:   # the normal control holds it now: its release puts the settings back
            self.precaution.pop(dev.id, None)
            self._pc_at.pop(self._pc_key(dev.id, shadow), None)
            self._pc_ok.pop(dev.id, None)
            return None
        if r is None or not r.available:
            return None   # keep, the maximum time still holds
        running = self._pc_running(dev, r)
        if running:
            if shadow:
                return self._pc_free(dev, now, self.t("pc_would_start", name=dev.name, room=max(0.0, room), kw=dev.start_kw))
            return self._pc_free(dev, now, self.t("pc_running", name=dev.name))
        if not r.allowed or (r.soc is not None and r.soc < dev.min_soc):   # condition says no, or the comfort value too low
            return self._pc_free(dev, now, self.t("pc_free", name=dev.name, room=max(0.0, room)))
        if not shadow and r.releasable and age >= PC_VERIFY_S:
            self._pc_rest[dev.id] = now + timedelta(minutes=MISS_REST_MIN)
            return self._pc_free(dev, now, self.t("pc_not_followed", name=dev.name, min=MISS_REST_MIN))
        if room < dev.start_kw + PC_HYST_KW:
            self._pc_ok.pop(dev.id, None)
            return None
        # released only after the headroom held 120 s, like the normal control gives back (cookers and kettles cycle)
        ok = self._pc_ok.setdefault(dev.id, now)
        if _secs(ok, now) >= ROOM_SUSTAIN_S and _secs(self._pc_last.get(dev.id), now) >= dev.start_gap_min * 60:
            key = "pc_would_free" if shadow else "pc_free"
            return self._pc_free(dev, now, self.t(key, name=dev.name, room=room))
        return None

    # ---------- confirmation: did the device really follow? ----------

    def _register(self, now: datetime, readings: dict[str, Reading], acts: list[Action]) -> None:
        """Remember what must show in the readings (only when the commands are really executed)."""
        if not self.real_effect:
            return
        for a in acts:
            dev = self.devices.get(a.device_id)
            if dev is None or not a.intervention:
                continue
            if a.kind == "set_current":
                r = readings.get(dev.id) or Reading()
                phase_switch = any(x.kind == "set_phase" and x.device_id == dev.id for x in acts)
                kw = float(a.value) * self._volts(self._phases(dev, r)) / 1000.0
                self._set_pending(dev.id, a, now, expect_kw=kw, power_after=PHASE_PAUSE_S if phase_switch else 0)
            elif a.kind in ("turn_off", "set_value", "battery_release", "wb_pause"):
                self._set_pending(dev.id, a, now)

    def _set_pending(self, dev_id: str, a: Action, now: datetime, **extra: Any) -> None:
        """A newer command for the same device replaces the expectation but not the waiting time: a device
        that ignores every command must not keep postponing its own check."""
        old = self._pending.get(dev_id)
        self._pending[dev_id] = {"act": a, "act_at": now, "since": old["since"] if old else now,
                                 "tries": old["tries"] if old else 0, **extra}

    def _followed(self, dev: DeviceConfig, pend: dict[str, Any], r: Reading | None, age: float) -> str:
        """'' if the reading shows the intervention, else what is wrong."""
        a: Action = pend["act"]
        if r is None or not r.available:
            return self.t("unreachable")
        if a.kind == "set_current":
            if r.current_a is None or r.current_a > float(a.value) + 0.5:
                return self.t("cur_not", cur=r.current_a, want=a.value) if r.current_a is not None else self.t("no_cur")
            if _secs(pend["act_at"], self._now) >= max(verify_wait(r), pend["power_after"]) - 5 and (r.power_w or 0.0) / 1000.0 > pend["expect_kw"] * 1.2 + 0.4:
                return self.t("power_despite", kw=(r.power_w or 0.0) / 1000.0, want=a.value)
        elif a.kind == "turn_off":
            if r.is_on is not False:
                return self.t("still_on")
        elif a.kind == "set_value":
            if r.value is None or abs(r.value - float(a.value)) > dev.step / 2 + 1e-9:
                return self.t("val_not", cur=r.value, want=float(a.value)) if r.value is not None else self.t("no_val")
        elif a.kind == "battery_release":
            if r.releasable:
                return self.t("rel_not")
        elif a.kind == "wb_pause":
            if (r.power_w or 0.0) > CHARGING_W:
                return self.t("still_charging", kw=(r.power_w or 0.0) / 1000.0)
        return ""

    def _verify(self, now: datetime, readings: dict[str, Reading]) -> list[Action]:
        """Check the pending interventions: repeat once, then report and leave the device alone for a while,
        so the next lever of the order is used instead of waiting for a device that does not react."""
        acts: list[Action] = []
        for dev_id in list(self._pending):
            pend, dev = self._pending[dev_id], self.devices.get(dev_id)
            if dev is None or dev_id not in self.interventions:
                del self._pending[dev_id]
                continue
            age = _secs(pend["since"], now)
            if age < verify_wait(readings.get(dev_id)) - 5:  # the cycle is 20 s, so the check happens at about 60 s
                continue
            problem = self._followed(dev, pend, readings.get(dev_id), age)
            if not problem:
                del self._pending[dev_id]
            elif pend["tries"] < 1:
                pend["tries"] += 1
                pend["since"] = pend["act_at"] = now
                a: Action = pend["act"]
                self._last_action = now
                if dev.kind in (KIND_WALLBOX, KIND_THROTTLE):
                    self._wbt(dev_id)["changed"] = now
                acts.append(Action(dev_id, a.kind, a.value, self.t("retry", name=dev.name, problem=problem), False))
            else:
                del self._pending[dev_id]
                self.misses += 1
                self._rest_until[dev_id] = now + timedelta(minutes=MISS_REST_MIN)
                if pend["act"].kind == "wb_pause":
                    self._pause_failed(dev_id, now)
                acts.append(Action(dev_id, "unconfirmed", None,
                                   self.t("miss", name=dev.name, problem=problem, min=MISS_REST_MIN), False))
        return acts

    def _pause_failed(self, dev_id: str, now: datetime) -> None:
        """A wallbox pause that did not show after its repetition (review 27.11.2026): the wallbox was never paused, so nothing is
        allowed again (its mode is not touched). The marker goes, else it would count as saved, show as paused and hold back the give-back
        of every other device; an intervention made only for the pause goes with it (an earlier lowering stays and is given back as
        usual). No new pause for PAUSE_USER_REST_MIN: a wallbox that ignores the command will not follow it ten minutes later either."""
        iv = self.interventions.get(dev_id)
        if not isinstance(iv, dict):
            return
        p = iv.pop("paused", None) or {}
        if p.get("new_iv"):
            del self.interventions[dev_id]
        self._pause_rest[dev_id] = now + timedelta(minutes=PAUSE_USER_REST_MIN)

    # ---------- savings estimate ----------

    def _saved_kw(self, readings: dict[str, Reading]) -> float:
        """Rough estimate of the power the current interventions keep out of the grid import (0 in observe mode).

        Wallbox: what its setting would allow at the original current minus what it can draw now (conservative:
        never less than the power it really draws). Switch: the power it had when it was switched off, while it
        is off. Script: the configured expected reduction.
        """
        if not self.real_effect or not self.interventions:
            return 0.0
        total = 0.0
        for dev_id, iv in self.interventions.items():
            dev, r = self.devices.get(dev_id), readings.get(dev_id)
            if dev is None or r is None:
                continue
            if dev.kind == KIND_WALLBOX:
                if iv.get("paused"):   # paused as the last measure: what it drew before
                    total += float(iv["paused"].get("kw") or 0.0)
                    continue
                p = (r.power_w or 0.0) / 1000.0
                if p < 1.0:
                    continue
                cur = r.current_a if r.current_a is not None else dev.max_current
                orig = float(iv.get("orig_current") or dev.max_current)
                phases = self._phases(dev, r)
                orig_phases = 3 if iv.get("switched") else phases   # a switch to one phase only ever comes from three
                orig_kw = orig * self._volts(orig_phases) / 1000.0
                cur_kw = cur * self._volts(phases) / 1000.0
                total += max(0.0, orig_kw - max(cur_kw, p))
            elif dev.kind == KIND_SWITCH:
                if r.is_on is False:
                    total += float(iv.get("watt") or dev.power_w) / 1000.0
            elif dev.kind == KIND_THROTTLE:
                cur = self._thr_value(dev, r)
                p = (r.power_w or 0.0) / 1000.0
                orig = float(iv.get("orig_value", dev.max_value))
                if p >= 0.3 and cur > 0 and orig > cur:
                    total += p * (orig / cur - 1.0)
            else:
                total += dev.power_w / 1000.0
        return round(total, 3)

    # ---------- reducing ----------

    def _options(self, now: datetime, readings: dict[str, Reading], excess: float, watched: bool = False) -> list[_Option]:
        """The levers that can lower the grid import now. `watched=True` returns the same for the devices set to observe only
        (they are never real levers)."""
        opts: list[_Option] = []
        for dev in self.devices.values():
            if dev.observe_only != watched:
                continue
            r = readings.get(dev.id)
            if r is None or not r.available or now < self._rest_until.get(dev.id, now):
                continue
            if dev.kind == KIND_WALLBOX:
                red = self._wb_reduction(dev, r, now)
                if red >= 0.1:
                    opts.append(_Option(dev, red))
            elif dev.kind == KIND_THROTTLE:
                red = self._thr_reduction(dev, r, now)
                if red >= 0.1:
                    opts.append(_Option(dev, red))
            elif dev.id in self.interventions or not r.allowed:
                continue
            elif dev.kind == KIND_SWITCH:
                pw = r.power_w if r.power_w is not None else (dev.power_w if r.is_on else 0.0)
                if r.is_on and pw >= dev.min_power_w and pw > 0:
                    opts.append(_Option(dev, pw / 1000.0))
            elif dev.kind == KIND_SCRIPT and dev.power_w > 0:
                opts.append(_Option(dev, dev.power_w / 1000.0))
            elif dev.kind in SETTING_KINDS and dev.power_w > 0:
                if r.releasable and (r.soc is None or r.soc >= dev.min_soc):
                    opts.append(_Option(dev, dev.power_w / 1000.0))
        return opts

    def _watch_notes(self, now: datetime, readings: dict[str, Reading], excess: float) -> list[Action]:
        """For each device set to observe only: once per quarter hour, what the guard would take from it right now."""
        notes: list[Action] = []
        for o in self._options(now, readings, excess, watched=True):
            key = (o.device.id, self.quarter)
            if key in self._watch_noted:
                continue
            self._watch_noted.add(key)
            dev, r = o.device, readings[o.device.id]
            if dev.kind in WALLBOX_KINDS:
                # the same step the guard would take with a real wallbox: only as much as is needed, not the whole lever
                cur, new, one_phase = self._wb_would(dev, r, min(excess + 0.2, o.reduction_kw + 0.2))
                if new >= cur and not one_phase:
                    self._watch_noted.discard(key)   # nothing to say yet: a later moment of this quarter hour may have
                    continue
                kw = min(excess, o.reduction_kw)
                key_t = "watch_wb1" if one_phase else "watch_wb"
                notes.append(Action(dev.id, "log", None, self.t(key_t, name=dev.name, cur=cur, new=new, kw=kw, excess=excess), False))
                continue
            notes.append(Action(o.device.id, "log", None, self.t("watch", name=o.device.name, kw=o.reduction_kw, excess=excess), False))
        if len(self._watch_noted) > 200:
            self._watch_noted = {k for k in self._watch_noted if k[1] == self.quarter}
        return notes

    def _choose(self, opts: list[_Option], excess: float) -> list[_Option]:
        if self.strategy == STRATEGY_ORDER:
            return sorted(opts, key=lambda o: (o.device.priority, -o.reduction_kw))
        need = excess + 0.1
        best: tuple | None = None
        best_set: list[_Option] = []
        for n in range(1, min(len(opts), 8) + 1):
            for combo in combinations(opts, n):
                total = sum(o.reduction_kw for o in combo)
                if total < need:
                    continue
                key = (sum(self._cost(o.device) for o in combo), n, -total)
                if best is None or key < best:
                    best, best_set = key, list(combo)
        if not best_set:
            best_set = list(opts)  # nothing is enough: use everything, gentlest first
        return sorted(best_set, key=lambda o: (self._cost(o.device), -o.reduction_kw))

    def _cost(self, dev: DeviceConfig) -> float:
        """Priority, plus a penalty for a device that was given back only minutes ago (no on/off flapping)."""
        back = self._restored.get(dev.id)
        return dev.priority + (10 if back is not None and back > self._now - timedelta(seconds=MIN_OFF_S) else 0)

    def _reduce(self, now, excess, readings, forecast, limit_kw, rest_h, smooth_only: bool = False) -> list[Action]:
        if _secs(self._last_action, now) < SETTLE_S:
            return []
        opts = self._options(now, readings, excess)
        if smooth_only:  # forecast-based: never switch devices off, only lower wallbox current and throttles
            opts = [o for o in opts if o.device.kind in (KIND_WALLBOX, KIND_THROTTLE)]
        notes: list[Action] = []
        if not smooth_only and any(d.may_pause for d in self.devices.values()):
            notes, paused = self._pause_step(now, readings, excess, opts)
            if paused:   # the last measure was taken (notes = the lines "would be paused" of observed devices, plus the pause)
                self._last_action = now
                return notes
        if not opts:
            if not smooth_only and forecast > limit_kw and rest_h < 0.1 and self._notified_q != self.quarter and not self.quarter_estimated:
                self._notified_q = self.quarter
                return notes + [Action("", "notify", round(forecast, 1),
                                       self.t("limit_lost", fc=forecast, limit=limit_kw))]
            return notes
        first = self._choose(opts, excess)[0]  # one step per cycle, gentlest of the chosen set first
        dev, r = first.device, readings[first.device.id]
        if dev.kind == KIND_WALLBOX:
            acts = self._wb_reduce(dev, r, min(excess + 0.2, first.reduction_kw + 0.2), now, excess)
        elif dev.kind == KIND_SWITCH:
            pw = r.power_w if r.power_w is not None else dev.power_w
            self.interventions[dev.id] = {"since": now.isoformat(), "watt": pw}
            acts = [Action(dev.id, "turn_off", None, self.t("sw_off", name=dev.name, w=pw, excess=excess))]
        elif dev.kind == KIND_THROTTLE:
            acts = self._thr_reduce(dev, r, min(excess + 0.2, first.reduction_kw + 0.2), now, excess)
        elif dev.kind == KIND_BATTERY:
            self.interventions[dev.id] = {"since": now.isoformat(), "soc": r.soc}
            soc = self.t("soc_part", soc=r.soc) if r.soc is not None else ""
            acts = [Action(dev.id, "battery_release", None, self.t("bat_rel", name=dev.name, excess=excess, soc=soc))]
        elif dev.kind == KIND_SETTING:
            self.interventions[dev.id] = {"since": now.isoformat(), "soc": r.soc}
            acts = [Action(dev.id, "battery_release", None, self.t("set_rel", name=dev.name, excess=excess))]
        else:
            self.interventions[dev.id] = {"since": now.isoformat()}
            acts = [Action(dev.id, "script_on", None, self.t("script_on", name=dev.name, excess=excess))]
        if acts:
            self._last_action = now
        return notes + acts

    # ---------- wallbox pause as the last measure (0.16.0, BETA) ----------

    def _pause_possible(self, dev: DeviceConfig, r: Reading, now: datetime, shadow: bool) -> bool:
        """The wallbox charges at its minimum current (a three-phase one with phase switching only after the switch to one phase)
        and may be paused now. In observe mode the readings never change: the current the guard would have set counts."""
        if not r.available or not r.allowed or r.paused:
            return False
        if now < self._rest_until.get(dev.id, now) or now < self._pause_rest.get(dev.id, now):
            return False
        iv = self.interventions.get(dev.id)
        if iv is not None and iv.get("paused"):
            return False
        if (r.power_w or 0.0) <= CHARGING_W:
            return False   # not charging: a pause brings nothing
        if not shadow and self._wb_locked(dev.id, now):
            return False
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        set_a = self._wbt(dev.id).get("set_a")
        if shadow and iv is not None and set_a is not None:
            cur = min(cur, int(set_a))
        if cur > self._wb_min(dev, r):
            return False
        return not (self._phases(dev, r) == 3 and dev.one_phase_option)

    def _pause_step(self, now: datetime, readings: dict[str, Reading], excess: float,
                    opts: list[_Option]) -> tuple[list[Action], bool]:
        """(actions, paused). Pause a wallbox that may be paused only when it is at its minimum, no other lever is left and that
        lasted PAUSE_AFTER_S. In observe mode or with *Observe only* at the device only the line "would be paused" (once per quarter
        hour, nothing is remembered)."""
        cands: list[DeviceConfig] = []
        for dev in self.devices.values():
            if dev.kind != KIND_WALLBOX or not dev.may_pause:
                continue
            r = readings.get(dev.id)
            shadow = not self.real_effect or dev.observe_only
            if r is None or not self._pause_possible(dev, r, now, shadow):
                self._wbt(dev.id).pop("pause_need", None)
                continue
            cands.append(dev)
        ids = {d.id for d in cands}
        if not cands or any(o.device.id not in ids for o in opts):
            for d in cands:   # another lever is left: it comes first, the wait starts again
                self._wbt(d.id).pop("pause_need", None)
            return [], False
        ready = []
        for dev in cands:
            t = self._wbt(dev.id)
            if t.get("pause_need") is None:
                t["pause_need"] = now
            if _secs(t["pause_need"], now) >= PAUSE_AFTER_S:
                ready.append(dev)
        notes: list[Action] = []
        real = [d for d in ready if self.real_effect and not d.observe_only]
        for dev in ready:
            key = (dev.id + "~pause", self.quarter)
            if dev in real or key in self._watch_noted:
                continue
            self._watch_noted.add(key)
            notes.append(Action(dev.id, "log", None, self.t("wb_would_pause", name=dev.name, excess=excess), False))
        if not real:
            return notes, False
        dev = sorted(real, key=lambda d: (d.priority, -(readings[d.id].power_w or 0.0)))[0]
        return notes + [self._pause(dev, readings[dev.id], now, excess)], True

    def _pause(self, dev: DeviceConfig, r: Reading, now: datetime, excess: float) -> Action:
        p_wb = (r.power_w or 0.0) / 1000.0
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        phases = self._phases(dev, r)
        new_iv = dev.id not in self.interventions   # nothing lowered before: the intervention exists only for the pause
        iv = self.interventions.setdefault(dev.id, {
            "since": now.isoformat(), "orig_current": cur, "orig_phase": r.phase_option,
            "one_phase": phases == 1, "switched": False, "phases": phases,
        })
        iv["paused"] = {"since": now.isoformat(), "mode": r.mode, "kw": round(p_wb, 3), "phases": phases, "new_iv": new_iv}
        t = self._wbt(dev.id)
        t["changed"] = now
        t.pop("pause_need", None)
        return Action(dev.id, "wb_pause", None, self.t("wb_pause", name=dev.name, excess=excess, kw=p_wb))

    def _wb_allow(self, dev: DeviceConfig, now: datetime, text: str) -> list[Action]:
        """Allow charging again with the mode from before (evcc) or the allow command; no new pause within the pause after taking
        back. The current stays at the minimum while the car starts (RESUME_WAIT_S), then the normal give-back raises it."""
        iv = self.interventions.get(dev.id) or {}
        p = iv.pop("paused", None) or {}
        t = self._wbt(dev.id)
        t["changed"] = t["resumed"] = now
        rest_s = dev.pause_min * 60 if dev.pause_min > 0 else MIN_OFF_S
        self._pause_rest[dev.id] = now + timedelta(seconds=rest_s)
        self._pending.pop(dev.id, None)
        return [Action(dev.id, "wb_resume", p.get("mode"), text, False)]

    def _resume_due(self, dev: DeviceConfig, r: Reading, room: float, now: datetime) -> list[Action]:
        p = self.interventions[dev.id]["paused"]
        hold = dev.hold_min * 60 if dev.hold_min > 0 else MIN_OFF_S
        try:
            since = datetime.fromisoformat(str(p.get("since")))
        except (TypeError, ValueError):
            since = None
        if _secs(since, now) < hold:
            return []
        need = self._wb_min(dev, r) * self._volts(int(p.get("phases") or 3)) / 1000.0 + PAUSE_MARGIN_KW
        if room <= need:
            return []
        return self._wb_allow(dev, now, self.t("wb_resume", name=dev.name, room=room))

    def _pause_watch_all(self, now: datetime, readings: dict[str, Reading]) -> list[Action]:
        acts: list[Action] = []
        for dev_id, iv in list(self.interventions.items()):
            dev = self.devices.get(dev_id)
            if dev is not None and dev.kind == KIND_WALLBOX and isinstance(iv, dict) and iv.get("paused"):
                acts += self._pause_watch(dev, readings.get(dev_id), now)
        return acts

    def _pause_watch(self, dev: DeviceConfig, r: Reading | None, now: datetime) -> list[Action]:
        """Every cycle while paused: allowed again at once when the switch was turned off; a pause someone ended meanwhile (another
        mode in evcc, the pause switch on again) stays theirs: nothing is sent, no new pause for PAUSE_USER_REST_MIN."""
        iv = self.interventions[dev.id]
        p = iv["paused"]
        if not dev.may_pause:
            return self._wb_allow(dev, now, self.t("wb_resume_now", name=dev.name))
        if r is None or r.paused is None:
            return []
        if r.paused:
            p["seen"] = True
            return []
        if not p.get("seen"):
            return []   # the pause has not shown yet (the check of the command decides)
        iv.pop("paused", None)
        self._pending.pop(dev.id, None)
        self._pause_rest[dev.id] = now + timedelta(minutes=PAUSE_USER_REST_MIN)
        return [Action(dev.id, "log", None, self.t("wb_pause_user", name=dev.name, min=PAUSE_USER_REST_MIN), False)]

    # ---------- throttle (stepless number) ----------

    @staticmethod
    def _thr_value(dev: DeviceConfig, r: Reading) -> float:
        return r.value if r.value is not None else dev.max_value

    def _thr_reduction(self, dev: DeviceConfig, r: Reading, now: datetime) -> float:
        """How many kW lowering to the minimum would bring (0 if not possible right now)."""
        if _secs(self._wbt(dev.id)["changed"], now) < WALLBOX_STEP_S:
            return 0.0
        if dev.id not in self.interventions and not r.allowed:
            return 0.0
        if r.soc is not None and r.soc < dev.min_soc:
            return 0.0
        cur = self._thr_value(dev, r)
        if cur <= dev.min_value + 1e-9 or cur <= 0:
            return 0.0
        p = (r.power_w or 0.0) / 1000.0
        if p >= 0.3:
            return max(0.0, p * (1.0 - dev.min_value / cur))
        span = max(dev.max_value - dev.min_value, 1e-9)
        return max(0.0, dev.power_w / 1000.0 * (cur - dev.min_value) / span)

    def _thr_reduce(self, dev: DeviceConfig, r: Reading, want_kw: float, now: datetime, excess: float) -> list[Action]:
        cur = self._thr_value(dev, r)
        p = (r.power_w or 0.0) / 1000.0
        if p >= 0.3:
            new = cur * max(0.0, p - want_kw) / p  # power follows the value
        else:
            new = cur - dev.step
        new = math.floor(new / dev.step + 1e-9) * dev.step
        if new >= cur:
            new = cur - dev.step
        new = max(dev.min_value, new)
        if new >= cur - 1e-9:
            return []
        self.interventions.setdefault(dev.id, {"since": now.isoformat(), "orig_value": cur})
        self._wbt(dev.id)["changed"] = now
        return [Action(dev.id, "set_value", new, self.t("thr_down", name=dev.name, cur=cur, new=new, excess=excess))]

    def _thr_release(self, dev: DeviceConfig, r: Reading, room: float, now: datetime, force: bool) -> list[Action]:
        iv = self.interventions[dev.id]
        t = self._wbt(dev.id)
        cur = self._thr_value(dev, r)
        orig = float(iv.get("orig_value", dev.max_value))
        if force:
            del self.interventions[dev.id]
            return [Action(dev.id, "set_value", orig, self.t("thr_back", name=dev.name, v=orig), False)]
        hold = max(WALLBOX_UP_AFTER_S, dev.hold_min * 60)
        if _secs(t["changed"], now) < hold:
            return []
        if cur >= orig - 1e-9:
            del self.interventions[dev.id]
            return [Action(dev.id, "log", None, self.t("free", name=dev.name), False)]
        p = (r.power_w or 0.0) / 1000.0
        if p >= 0.3 and cur > 0:
            per_step = p * dev.step / cur
        else:
            per_step = dev.power_w / 1000.0 * dev.step / max(dev.max_value - dev.min_value, 1e-9)
        if room <= per_step + 0.15:
            return []
        new = min(orig, cur + dev.step)
        t["changed"] = now
        acts = [Action(dev.id, "set_value", new, self.t("thr_up", name=dev.name, cur=cur, new=new), False)]
        if new >= orig - 1e-9:
            del self.interventions[dev.id]
        return acts

    # ---------- wallbox ----------

    def _wbt(self, dev_id: str) -> dict[str, datetime | None]:
        return self._wb.setdefault(dev_id, {"changed": None, "phase": None, "too_little": None, "room3": None})

    def _phases(self, dev: DeviceConfig, r: Reading) -> int:
        """1, 2 or 3. Two only when the source reports exactly two (a car that charges on two phases, field case 26.11.2026);
        unknown or more than three counts as three, as before."""
        iv = self.interventions.get(dev.id)
        if iv is not None and "one_phase" in iv:
            if iv["one_phase"]:
                return 1   # what the guard set; the "phases in use" sensor lags
            # the phases at the start of the intervention (saved since 0.16.0); an intervention saved before has none
            return int(iv.get("phases") or (2 if r.phases == 2 else 3))
        if dev.one_phase_option and r.phase_option == dev.one_phase_option:
            return 1
        if r.phases is not None and r.phases < 2:
            return 1
        if r.phases == 2:
            return 2
        return 3

    def _volts(self, phases: int) -> float:
        """Volts times phases: what one amp gives in W (v1, 2 x v1 or v3)."""
        return self.v1 if phases == 1 else self.v3 if phases == 3 else phases * self.v1

    def _wb_locked(self, dev_id: str, now: datetime) -> bool:
        t = self._wbt(dev_id)
        return _secs(t["changed"], now) < WALLBOX_STEP_S or _secs(t["phase"], now) < PHASE_PAUSE_S

    def _charging(self, dev_id: str, r: Reading, now: datetime) -> bool:
        t = self._wbt(dev_id)
        return ((r.power_w or 0.0) > CHARGING_W or _secs(t["phase"], now) < PHASE_PAUSE_S + 60
                or _secs(t.get("resumed"), now) < RESUME_WAIT_S)

    def _wb_reduction(self, dev: DeviceConfig, r: Reading, now: datetime) -> float:
        p_wb = (r.power_w or 0.0) / 1000.0
        if p_wb < 1.0 or self._wb_locked(dev.id, now):
            return 0.0
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        t = self._wbt(dev.id)
        lo = self._wb_min(dev, r)
        phases = self._phases(dev, r)
        if phases == 2:   # two phases: only down to the minimum, never to one phase (see _wb_reduce)
            return max(0.0, p_wb - lo * self._volts(2) / 1000.0) if cur > lo else 0.0
        if phases == 3:
            if cur > lo:
                return max(0.0, p_wb - lo * self.v3 / 1000.0)
            if self._smooth:
                return 0.0  # a forecast alone never switches to 1 phase (that pauses charging)
            if t["too_little"] is None:
                t["too_little"] = now
            if dev.one_phase_option and _secs(t["too_little"], now) >= TO_ONE_PHASE_AFTER_S:
                return max(0.0, p_wb - lo * self.v1 / 1000.0)
            return 0.0  # wait: maybe only the microwave; other devices may help meanwhile
        if cur > lo:
            return max(0.0, p_wb - lo * self.v1 / 1000.0)
        return 0.0

    @staticmethod
    def _wb_min(dev: DeviceConfig, r: Reading) -> int:
        """The lowest current the guard may set: the configured minimum, or with a list of currents its entry for it - the
        lowest entry when the list starts above the minimum (list from 8 A, minimum 6 A: 8). Without this the guard waited
        for a step the wallbox does not have and neither switched to one phase nor let other devices help."""
        return step_down(dev.min_current, r.current_steps)

    def _wb_would(self, dev: DeviceConfig, r: Reading, want_kw: float) -> tuple[int, int, bool]:
        """(current now, current the guard would set, switch to one phase) for a reduction of `want_kw` - the arithmetic of
        `_wb_reduce` without touching anything (for devices set to observe only)."""
        p_wb = (r.power_w or 0.0) / 1000.0
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        goal = p_wb - want_kw
        lo, steps = self._wb_min(dev, r), r.current_steps
        phases = self._phases(dev, r)
        if phases == 2:
            a = int(goal * 1000.0 / self._volts(2))
            return cur, min(cur, max(step_down(a, steps), lo)), False
        if phases == 3:
            a = int(goal * 1000.0 / self.v3)
            if a >= lo:
                return cur, min(cur, max(step_down(a, steps), lo)), False
            if cur > lo:
                return cur, lo, False
            if dev.one_phase_option:
                return cur, step_down(_clamp(int(goal * 1000.0 / self.v1), lo, dev.max_current), steps), True
            return cur, cur, False
        return cur, min(cur, step_down(_clamp(int(goal * 1000.0 / self.v1), lo, dev.max_current), steps)), False

    def _wb_reduce(self, dev: DeviceConfig, r: Reading, want_kw: float, now: datetime, excess: float) -> list[Action]:
        p_wb = (r.power_w or 0.0) / 1000.0
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        phases = self._phases(dev, r)
        t = self._wbt(dev.id)
        goal = p_wb - want_kw
        acts: list[Action] = []
        lo = self._wb_min(dev, r)
        if phases == 2:
            # Two phases (the car charges on two, e.g. its charger has two): only the current is lowered. No switch to one phase:
            # the way back (_wb_release) knows only one and three phases, and the few amps it would bring are not worth a pause
            a = max(step_down(int(goal * 1000.0 / self._volts(2)), r.current_steps), lo)
            if a < cur:
                acts = [Action(dev.id, "set_current", a, self.t("wb2_down", name=dev.name, cur=cur, new=a, excess=excess))]
        elif phases == 3:
            a = int(goal * 1000.0 / self.v3)
            if a >= lo:
                a = max(step_down(a, r.current_steps), lo)
                if a < cur:
                    acts = [Action(dev.id, "set_current", a, self.t("wb3_down", name=dev.name, cur=cur, new=a, excess=excess))]
            elif cur > lo:
                t["too_little"] = now
                acts = [Action(dev.id, "set_current", lo, self.t("wb3_down", name=dev.name, cur=cur, new=lo, excess=excess))]
            elif dev.one_phase_option:
                a1 = step_down(_clamp(int(goal * 1000.0 / self.v1), lo, dev.max_current), r.current_steps)
                acts = [Action(dev.id, "set_current", a1, ""),
                        Action(dev.id, "set_phase", dev.one_phase_option,
                               self.t("wb_to1", name=dev.name, a=a1, excess=excess))]
                t["too_little"] = None
                t["phase"] = now
        else:
            a1 = step_down(_clamp(int(goal * 1000.0 / self.v1), lo, dev.max_current), r.current_steps)
            if a1 < cur:
                acts = [Action(dev.id, "set_current", a1, self.t("wb1_down", name=dev.name, cur=cur, new=a1))]
        if acts:
            iv = self.interventions.setdefault(dev.id, {
                "since": now.isoformat(), "orig_current": cur, "orig_phase": r.phase_option,
                "one_phase": phases == 1, "switched": False, "phases": phases,
            })
            if any(x.kind == "set_phase" for x in acts):
                iv["one_phase"] = iv["switched"] = True
            t["changed"] = now
            t["set_a"] = next(int(x.value) for x in acts if x.kind == "set_current")   # observe mode: what it would be now
        return acts

    def _wb_release(self, dev: DeviceConfig, r: Reading, room: float, now: datetime, force: bool) -> list[Action]:
        iv = self.interventions[dev.id]
        if iv.get("paused"):
            if not force:
                return []   # a pause is given back by _release first (_resume_due), never by the normal give-back
            return self._wb_allow(dev, now, self.t("wb_resume_now", name=dev.name)) + self._wb_release(dev, r, room, now, True)
        t = self._wbt(dev.id)
        if not force and _secs(t.get("resumed"), now) < RESUME_WAIT_S:
            return []   # allowed again after a pause: the car starts at the minimum current, raised only afterwards
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        orig = int(iv.get("orig_current") or dev.max_current)
        if force or not self._charging(dev.id, r, now):
            acts = [Action(dev.id, "set_current", orig, self.t("wb_back", name=dev.name, a=orig), False)]
            if iv.get("switched") and iv.get("orig_phase"):
                acts.append(Action(dev.id, "set_phase", iv["orig_phase"], self.t("wb_phase_back", name=dev.name, opt=iv["orig_phase"]), False))
                t["phase"] = now
            del self.interventions[dev.id]
            t["changed"] = now
            return acts
        if _secs(t["changed"], now) < WALLBOX_UP_AFTER_S or self._wb_locked(dev.id, now):
            return []
        if iv.get("one_phase"):
            p_wb = (r.power_w or 0.0) / 1000.0
            lo = self._wb_min(dev, r)
            if iv.get("switched") and iv.get("orig_phase") and room > (lo * self.v3 / 1000.0 - p_wb) + 0.5:
                if t["room3"] is None:
                    t["room3"] = now
                if _secs(t["room3"], now) < TO_THREE_PHASE_AFTER_S:
                    return []
                t["room3"] = None
                iv["one_phase"] = iv["switched"] = False
                t["changed"] = t["phase"] = now
                return [Action(dev.id, "set_current", lo, "", False),
                        Action(dev.id, "set_phase", iv["orig_phase"],
                               self.t("wb_to3", name=dev.name, a=lo), False)]
            t["room3"] = None
            top = dev.max_current if iv.get("switched") else orig
            if cur < top and room > self.v1 / 1000.0 + 0.15:
                new = step_down(min(top, cur + max(1, int((room - 0.15) * 1000.0 / self.v1))), r.current_steps)
                if new <= cur:   # the next step of the list does not fit yet
                    return []
                t["changed"] = now
                acts = [Action(dev.id, "set_current", new, self.t("wb1_up", name=dev.name, cur=cur, new=new), False)]
                if not iv.get("switched") and new >= orig:
                    del self.interventions[dev.id]
                return acts
            return []
        vn = self._volts(self._phases(dev, r))   # three phases, or two (field case 26.11.2026)
        if room > vn / 1000.0 + 0.15 and cur < orig:
            new = step_down(min(orig, cur + max(1, int((room - 0.15) * 1000.0 / vn))), r.current_steps)
            if new <= cur:   # the next step of the list does not fit yet
                return []
            t["changed"] = now
            acts = [Action(dev.id, "set_current", new, self.t("wb3_up", name=dev.name, cur=cur, new=new), False)]
            if new >= orig:
                del self.interventions[dev.id]
                acts.append(Action(dev.id, "log", None, self.t("free_a", name=dev.name, a=new), False))
            return acts
        if cur >= orig:
            del self.interventions[dev.id]  # someone else raised it meanwhile
            return [Action(dev.id, "log", None, self.t("free", name=dev.name), False)]
        return []

    # ---------- releasing ----------

    def _release_one(self, dev: DeviceConfig, r: Reading, room: float, now: datetime, force: bool) -> list[Action]:
        had = dev.id in self.interventions
        acts = self._release_one_inner(dev, r, room, now, force)
        # (a wallbox has the field only for its pause since 0.16.0: there it is the wait before the next pause, see _wb_allow)
        if had and dev.id not in self.interventions and dev.pause_min > 0 and dev.kind != KIND_WALLBOX:
            self._rest_until[dev.id] = now + timedelta(minutes=dev.pause_min)  # protect e.g. a compressor
        return acts

    def _release_one_inner(self, dev: DeviceConfig, r: Reading, room: float, now: datetime, force: bool) -> list[Action]:
        iv = self.interventions[dev.id]
        if dev.kind == KIND_WALLBOX:
            return self._wb_release(dev, r, room, now, force)
        if dev.kind == KIND_THROTTLE:
            return self._thr_release(dev, r, room, now, force)
        hold = dev.hold_min * 60 if dev.hold_min > 0 else MIN_OFF_S
        if not force and _secs(datetime.fromisoformat(iv["since"]), now) < hold:
            return []
        if dev.kind == KIND_SWITCH:
            need = float(iv.get("watt") or dev.power_w) / 1000.0 + 0.1
            if not force and room <= need:
                return []
            del self.interventions[dev.id]
            if r.is_on is False and r.restore_allowed and r.available:
                return [Action(dev.id, "turn_on", None, self.t("sw_on", name=dev.name), False)]
            return [Action(dev.id, "log", None, self.t("sw_stays", name=dev.name), False)]
        need = dev.power_w / 1000.0
        if not force and room <= need:
            return []
        del self.interventions[dev.id]
        if dev.kind in SETTING_KINDS:
            return [Action(dev.id, "battery_restore", None, self.t("bat_back", name=dev.name), False)]
        return [Action(dev.id, "script_off", None, self.t("script_off", name=dev.name), False)]

    def _release(self, now: datetime, room: float, readings: dict[str, Reading]) -> list[Action]:
        if not self.interventions or _secs(self._last_release, now) < RELEASE_EVERY_S or _secs(self._last_action, now) < SETTLE_S:
            return []
        paused = [i for i, iv in self.interventions.items() if isinstance(iv, dict) and iv.get("paused") and i in self.devices]
        if paused:   # the last measure is taken back first; everything else waits for it (reverse order)
            dev_id = max(paused, key=lambda i: str(self.interventions[i]["paused"].get("since")))
            dev, r = self.devices[dev_id], readings.get(dev_id) or Reading(available=False)
            acts = self._resume_due(dev, r, room, now)
            if acts:
                self._last_release = now
            return acts
        # strictly the most important device first: a less important one gets no headroom while a more
        # important one is still waiting (only a wallbox that stopped charging is always given back)
        for dev_id in sorted(self.interventions, key=lambda i: -self.devices[i].priority):
            dev, r = self.devices[dev_id], readings.get(dev_id) or Reading(available=False)
            acts = self._release_one(dev, r, room, now, False)
            if acts:
                self._last_release = now
                if dev_id not in self.interventions:
                    self._restored[dev_id] = now
                return acts
            if dev.kind != KIND_WALLBOX:
                break
        for dev_id in list(self.interventions):
            dev, r = self.devices[dev_id], readings.get(dev_id) or Reading(available=False)
            if dev.kind == KIND_WALLBOX and not self._charging(dev_id, r, now):
                self._last_release = now
                return self._release_one(dev, r, -1.0, now, False)
        return []

    def _forced_releases(self, now: datetime, readings: dict[str, Reading]) -> list[Action]:
        acts: list[Action] = []
        for dev_id in list(self.interventions):
            dev = self.devices[dev_id]
            r = readings.get(dev_id)
            if dev.kind == KIND_WALLBOX and self.interventions[dev_id].get("paused"):
                continue   # see _pause_watch_all
            if dev.kind in GUARDED_KINDS and r is not None and r.soc is not None and r.soc < dev.min_soc:
                what = self.t("word_soc") if dev.kind == KIND_BATTERY else self.t("word_guard")
                acts.append(Action(dev_id, "log", None, self.t("below_min", name=dev.name, what=what, v=r.soc, min=dev.min_soc), False))
                acts += self._release_one(dev, r, 0.0, now, True)
                self._rest_until[dev_id] = now + timedelta(minutes=10)
                continue
            if dev.kind == KIND_WALLBOX or dev.max_off_min <= 0:
                continue
            since = datetime.fromisoformat(self.interventions[dev_id]["since"])
            if (now - since).total_seconds() >= dev.max_off_min * 60:
                acts.append(Action(dev_id, "log", None, self.t("max_off", name=dev.name, min=dev.max_off_min), False))
                acts += self._release_one(dev, readings.get(dev_id) or Reading(available=False), 0.0, now, True)
                self._rest_until[dev_id] = now + timedelta(minutes=dev.max_off_min)
        return acts

    def release_all(self, now: datetime, readings: dict[str, Reading], reason: str = "") -> list[Action]:
        acts: list[Action] = []
        for dev_id in sorted(list(self.interventions), key=lambda i: -self.devices[i].priority):
            acts += self._release_one(self.devices[dev_id], readings.get(dev_id) or Reading(available=False), 99.0, now, True)
        for dev_id in list(self.precaution):   # precautionary locks too (empty without a device with a start power)
            dev = self.devices.get(dev_id)
            if dev is None:
                self.precaution.pop(dev_id, None)
                continue
            acts.append(self._pc_free(dev, now, self.t("pc_back", name=dev.name)))
        if acts and reason:
            acts.insert(0, Action("", "log", None, self.t("all_free", reason=reason), False))
        for t in self._wb.values():
            t["too_little"] = t["room3"] = None
        return acts

    def forget(self) -> None:
        """Drop interventions without touching devices (they were only simulated in observe mode)."""
        self.interventions = {}
        self._pending = {}
        self._wb = {}
        self._last_action = self._last_release = None
        self.precaution = {}
        self._pc_last = {}
        self._pc_rest = {}
        self._pc_ok = {}
        self._pc_at = {}
        # the daily sums of real locks stay (a change of the mode does not give a new day); observed ones are dropped
        self._pc_day = {k: v for k, v in self._pc_day.items() if not k.endswith(PC_OBSERVED)}
