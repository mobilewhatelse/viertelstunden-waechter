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
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import combinations
from typing import Any

V1 = 230.0
V3 = 3 * 230.0

KIND_WALLBOX = "wallbox"
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
MAX_PLAUSIBLE_KW = 60.0       # counter jumps after an outage are not real peaks
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


class Guard:
    """Keeps the quarter-hour average of the grid import below a target."""

    def __init__(self, devices: list[DeviceConfig], strategy: str = STRATEGY_COMFORT, voltage: float = V1) -> None:
        self.v1 = float(voltage)          # voltage of one phase (230 V in Europe)
        self.v3 = 3.0 * float(voltage)    # three phases
        self.devices: dict[str, DeviceConfig] = {d.id: d for d in devices}
        self.strategy = strategy
        self.interventions: dict[str, dict[str, Any]] = {}
        self.quarter: datetime | None = None
        self.energy_kwh = 0.0
        self.finished_quarter_kw: float | None = None  # set in the cycle in which a quarter hour ended
        self.values: dict[str, Any] = {}
        self.state = "ready"
        self._counter_at_q: float | None = None
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
        self._now = datetime.min

    # ---------- persistence ----------

    def to_dict(self) -> dict[str, Any]:
        return {"interventions": self.interventions}

    def load(self, d: dict[str, Any]) -> None:
        self.interventions = {k: v for k, v in (d.get("interventions") or {}).items() if k in self.devices}

    # ---------- quarter-hour accounting ----------

    def _account(self, now: datetime, grid_kw: float | None, counter_kwh: float | None) -> None:
        self.finished_quarter_kw = None
        self.finished_unguarded_kw = None
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
            self.quarter = q
            self.energy_kwh = 0.0
            self.saved_kwh = 0.0
            self._notified_q = None
            if first:
                # started in the middle of a quarter hour: estimate what came before with the current power
                self.energy_kwh = (grid_kw or 0.0) * (now - q).total_seconds() / 3600.0
                self._last_t = now
            else:
                self._last_t = q
            self._counter_at_q = counter_kwh - self.energy_kwh if counter_kwh is not None else None
        if grid_kw is not None and self._last_t is not None:
            dt = max(0.0, min(60.0, (now - self._last_t).total_seconds()))
            self.energy_kwh += self._last_p * dt / 3600.0
            self.saved_kwh += self._last_saved * dt / 3600.0
        if counter_kwh is not None:
            if self._counter_at_q is None:
                self._counter_at_q = counter_kwh - self.energy_kwh
            diff = counter_kwh - self._counter_at_q
            elapsed_h = max(1.0, (now - q).total_seconds()) / 3600.0
            if 0.0 <= diff <= MAX_PLAUSIBLE_KW * elapsed_h + 0.05:
                self.energy_kwh = max(self.energy_kwh, diff)  # the counter is the better source; take the larger (careful)
        if grid_kw is not None:
            self._last_t, self._last_p = now, grid_kw

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
    ) -> list[Action]:
        self._now = now
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
        self.values = {
            "limit_kw": limit_kw,
            "target_kw": round(target, 2),
            "grid_kw": round(p, 3),
            "quarter_energy_kwh": round(self.energy_kwh, 3),
            "allowed_kw": round(allowed, 2),
            "forecast_kw": round(forecast, 2),
            "quarter": self.quarter,
        }
        self._last_saved = self._saved_kw(readings)
        self.values["saved_kw"] = round(self._last_saved, 2)

        if grid_kw is None:
            if self._missing_since is None:
                self._missing_since = now
            if _secs(self._missing_since, now) >= MISSING_DATA_S:
                self.state = "no_data"
                return self.release_all(now, readings, "Messwerte fehlen")
            return []
        self._missing_since = None

        if not enabled:
            self.state = "idle"
            return self.release_all(now, readings, "nicht nötig") if self.interventions else []

        # headroom that fits permanently (not the rest budget near :15): average of the last two minutes,
        # counted only since the last change, so a release is judged on the situation after the previous one
        changed = max([t for t in (self._last_action, self._last_release) if t is not None], default=None)
        slow = [x for x in self._p_hist if changed is None or x[0] > changed]
        held = bool(slow) and _secs(slow[0][0], now) >= ROOM_SUSTAIN_S - STEP_TOLERANCE_S
        room = min(allowed, target) - sum(x[1] for x in slow) / len(slow) if held else -1.0
        self.values["room_kw"] = round(room, 2)

        actions = self._forced_releases(now, readings)
        if not actions:
            if excess > 0.1:
                actions = self._reduce(now, excess, readings, forecast, limit_kw, rest_h)
            else:
                if room > 0:  # only real, lasting headroom ends the wait for 1-phase (a cooker's off-phase does not)
                    for t in self._wb.values():
                        t["too_little"] = None
                actions = self._release(now, room, readings)
        self.state = "intervening" if self.interventions else "ready"
        return actions

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
                p = (r.power_w or 0.0) / 1000.0
                if p < 1.0:
                    continue
                cur = r.current_a if r.current_a is not None else dev.max_current
                orig = float(iv.get("orig_current") or dev.max_current)
                phases = self._phases(dev, r)
                orig_phases = 3 if iv.get("switched") else phases
                orig_kw = orig * (self.v3 if orig_phases == 3 else self.v1) / 1000.0
                cur_kw = cur * (self.v3 if phases == 3 else self.v1) / 1000.0
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

    def _options(self, now: datetime, readings: dict[str, Reading], excess: float) -> list[_Option]:
        opts: list[_Option] = []
        for dev in self.devices.values():
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

    def _reduce(self, now, excess, readings, forecast, limit_kw, rest_h) -> list[Action]:
        if _secs(self._last_action, now) < SETTLE_S:
            return []
        opts = self._options(now, readings, excess)
        if not opts:
            if forecast > limit_kw and rest_h < 0.1 and self._notified_q != self.quarter:
                self._notified_q = self.quarter
                return [Action("", "notify", round(forecast, 1),
                               f"Grenze nicht zu halten: Prognose {forecast:.1f} kW (Grenze {limit_kw:.1f} kW), alle Hebel ausgeschöpft")]
            return []
        first = self._choose(opts, excess)[0]  # one step per cycle, gentlest of the chosen set first
        dev, r = first.device, readings[first.device.id]
        if dev.kind == KIND_WALLBOX:
            acts = self._wb_reduce(dev, r, min(excess + 0.2, first.reduction_kw + 0.2), now, excess)
        elif dev.kind == KIND_SWITCH:
            pw = r.power_w if r.power_w is not None else dev.power_w
            self.interventions[dev.id] = {"since": now.isoformat(), "watt": pw}
            acts = [Action(dev.id, "turn_off", None, f"{dev.name} aus ({pw:.0f} W, {excess:.1f} kW zu viel)")]
        elif dev.kind == KIND_THROTTLE:
            acts = self._thr_reduce(dev, r, min(excess + 0.2, first.reduction_kw + 0.2), now, excess)
        elif dev.kind == KIND_BATTERY:
            self.interventions[dev.id] = {"since": now.isoformat(), "soc": r.soc}
            soc = f", Ladestand {r.soc:.0f} %" if r.soc is not None else ""
            acts = [Action(dev.id, "battery_release", None, f"{dev.name}: Batterie freigegeben ({excess:.1f} kW zu viel{soc})")]
        elif dev.kind == KIND_SETTING:
            self.interventions[dev.id] = {"since": now.isoformat(), "soc": r.soc}
            acts = [Action(dev.id, "battery_release", None, f"{dev.name}: Einstellung geändert ({excess:.1f} kW zu viel)")]
        else:
            self.interventions[dev.id] = {"since": now.isoformat()}
            acts = [Action(dev.id, "script_on", None, f"{dev.name}: Notfall-Eingriff ({excess:.1f} kW zu viel)")]
        if acts:
            self._last_action = now
        return acts

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
        return [Action(dev.id, "set_value", new, f"{dev.name} {cur:g} → {new:g} ({excess:.1f} kW zu viel)")]

    def _thr_release(self, dev: DeviceConfig, r: Reading, room: float, now: datetime, force: bool) -> list[Action]:
        iv = self.interventions[dev.id]
        t = self._wbt(dev.id)
        cur = self._thr_value(dev, r)
        orig = float(iv.get("orig_value", dev.max_value))
        if force:
            del self.interventions[dev.id]
            return [Action(dev.id, "set_value", orig, f"{dev.name} wieder {orig:g}", False)]
        hold = max(WALLBOX_UP_AFTER_S, dev.hold_min * 60)
        if _secs(t["changed"], now) < hold:
            return []
        if cur >= orig - 1e-9:
            del self.interventions[dev.id]
            return [Action(dev.id, "log", None, f"{dev.name} wieder frei", False)]
        p = (r.power_w or 0.0) / 1000.0
        if p >= 0.3 and cur > 0:
            per_step = p * dev.step / cur
        else:
            per_step = dev.power_w / 1000.0 * dev.step / max(dev.max_value - dev.min_value, 1e-9)
        if room <= per_step + 0.15:
            return []
        new = min(orig, cur + dev.step)
        t["changed"] = now
        acts = [Action(dev.id, "set_value", new, f"{dev.name} {cur:g} → {new:g} (wieder mehr Luft)", False)]
        if new >= orig - 1e-9:
            del self.interventions[dev.id]
        return acts

    # ---------- wallbox ----------

    def _wbt(self, dev_id: str) -> dict[str, datetime | None]:
        return self._wb.setdefault(dev_id, {"changed": None, "phase": None, "too_little": None, "room3": None})

    def _phases(self, dev: DeviceConfig, r: Reading) -> int:
        iv = self.interventions.get(dev.id)
        if iv is not None and "one_phase" in iv:
            return 1 if iv["one_phase"] else 3  # what the guard set; the "phases in use" sensor lags
        if dev.one_phase_option and r.phase_option == dev.one_phase_option:
            return 1
        if r.phases is not None and r.phases < 2:
            return 1
        return 3

    def _wb_locked(self, dev_id: str, now: datetime) -> bool:
        t = self._wbt(dev_id)
        return _secs(t["changed"], now) < WALLBOX_STEP_S or _secs(t["phase"], now) < PHASE_PAUSE_S

    def _charging(self, dev_id: str, r: Reading, now: datetime) -> bool:
        return (r.power_w or 0.0) > CHARGING_W or _secs(self._wbt(dev_id)["phase"], now) < PHASE_PAUSE_S + 60

    def _wb_reduction(self, dev: DeviceConfig, r: Reading, now: datetime) -> float:
        p_wb = (r.power_w or 0.0) / 1000.0
        if p_wb < 1.0 or self._wb_locked(dev.id, now):
            return 0.0
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        t = self._wbt(dev.id)
        if self._phases(dev, r) == 3:
            if cur > dev.min_current:
                return max(0.0, p_wb - dev.min_current * self.v3 / 1000.0)
            if t["too_little"] is None:
                t["too_little"] = now
            if dev.one_phase_option and _secs(t["too_little"], now) >= TO_ONE_PHASE_AFTER_S:
                return max(0.0, p_wb - dev.min_current * self.v1 / 1000.0)
            return 0.0  # wait: maybe only the microwave; other devices may help meanwhile
        if cur > dev.min_current:
            return max(0.0, p_wb - dev.min_current * self.v1 / 1000.0)
        return 0.0

    def _wb_reduce(self, dev: DeviceConfig, r: Reading, want_kw: float, now: datetime, excess: float) -> list[Action]:
        p_wb = (r.power_w or 0.0) / 1000.0
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        phases = self._phases(dev, r)
        t = self._wbt(dev.id)
        goal = p_wb - want_kw
        acts: list[Action] = []
        if phases == 3:
            a = int(goal * 1000.0 / self.v3)
            if a >= dev.min_current:
                if a < cur:
                    acts = [Action(dev.id, "set_current", a, f"{dev.name} {cur} A -> {a} A (3-phasig, {excess:.1f} kW zu viel)")]
            elif cur > dev.min_current:
                t["too_little"] = now
                acts = [Action(dev.id, "set_current", dev.min_current,
                               f"{dev.name} {cur} A -> {dev.min_current} A (3-phasig, {excess:.1f} kW zu viel)")]
            elif dev.one_phase_option:
                a1 = _clamp(int(goal * 1000.0 / self.v1), dev.min_current, dev.max_current)
                acts = [Action(dev.id, "set_current", a1, ""),
                        Action(dev.id, "set_phase", dev.one_phase_option,
                               f"{dev.name} auf 1-phasig {a1} A ({excess:.1f} kW zu viel), kurze Ladepause durch Phasenwechsel")]
                t["too_little"] = None
                t["phase"] = now
        else:
            a1 = _clamp(int(goal * 1000.0 / self.v1), dev.min_current, dev.max_current)
            if a1 < cur:
                acts = [Action(dev.id, "set_current", a1, f"{dev.name} 1-phasig {cur} A -> {a1} A")]
        if acts:
            iv = self.interventions.setdefault(dev.id, {
                "since": now.isoformat(), "orig_current": cur, "orig_phase": r.phase_option,
                "one_phase": phases == 1, "switched": False,
            })
            if any(x.kind == "set_phase" for x in acts):
                iv["one_phase"] = iv["switched"] = True
            t["changed"] = now
        return acts

    def _wb_release(self, dev: DeviceConfig, r: Reading, room: float, now: datetime, force: bool) -> list[Action]:
        iv = self.interventions[dev.id]
        t = self._wbt(dev.id)
        cur = int(r.current_a if r.current_a is not None else dev.max_current)
        orig = int(iv.get("orig_current") or dev.max_current)
        if force or not self._charging(dev.id, r, now):
            acts = [Action(dev.id, "set_current", orig, f"{dev.name} wieder {orig} A", False)]
            if iv.get("switched") and iv.get("orig_phase"):
                acts.append(Action(dev.id, "set_phase", iv["orig_phase"], f"{dev.name} wieder {iv['orig_phase']}", False))
                t["phase"] = now
            del self.interventions[dev.id]
            t["changed"] = now
            return acts
        if _secs(t["changed"], now) < WALLBOX_UP_AFTER_S or self._wb_locked(dev.id, now):
            return []
        if iv.get("one_phase"):
            p_wb = (r.power_w or 0.0) / 1000.0
            if iv.get("switched") and iv.get("orig_phase") and room > (dev.min_current * self.v3 / 1000.0 - p_wb) + 0.5:
                if t["room3"] is None:
                    t["room3"] = now
                if _secs(t["room3"], now) < TO_THREE_PHASE_AFTER_S:
                    return []
                t["room3"] = None
                iv["one_phase"] = iv["switched"] = False
                t["changed"] = t["phase"] = now
                return [Action(dev.id, "set_current", dev.min_current, "", False),
                        Action(dev.id, "set_phase", iv["orig_phase"],
                               f"{dev.name} wieder 3-phasig ({dev.min_current} A), kurze Ladepause durch Phasenwechsel", False)]
            t["room3"] = None
            top = dev.max_current if iv.get("switched") else orig
            if cur < top and room > self.v1 / 1000.0 + 0.15:
                new = min(top, cur + max(1, int((room - 0.15) * 1000.0 / self.v1)))
                t["changed"] = now
                acts = [Action(dev.id, "set_current", new, f"{dev.name} 1-phasig {cur} A -> {new} A (wieder mehr Luft)", False)]
                if not iv.get("switched") and new >= orig:
                    del self.interventions[dev.id]
                return acts
            return []
        if room > self.v3 / 1000.0 + 0.15 and cur < orig:
            new = min(orig, cur + max(1, int((room - 0.15) * 1000.0 / self.v3)))
            t["changed"] = now
            acts = [Action(dev.id, "set_current", new, f"{dev.name} {cur} A -> {new} A (wieder mehr Luft)", False)]
            if new >= orig:
                del self.interventions[dev.id]
                acts.append(Action(dev.id, "log", None, f"{dev.name} wieder frei ({new} A)", False))
            return acts
        if cur >= orig:
            del self.interventions[dev.id]  # someone else raised it meanwhile
            return [Action(dev.id, "log", None, f"{dev.name} wieder frei", False)]
        return []

    # ---------- releasing ----------

    def _release_one(self, dev: DeviceConfig, r: Reading, room: float, now: datetime, force: bool) -> list[Action]:
        had = dev.id in self.interventions
        acts = self._release_one_inner(dev, r, room, now, force)
        if had and dev.id not in self.interventions and dev.pause_min > 0:
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
                return [Action(dev.id, "turn_on", None, f"{dev.name} wieder an", False)]
            return [Action(dev.id, "log", None, f"{dev.name} bleibt aus (Zeitplan oder inzwischen anders geschaltet)", False)]
        need = dev.power_w / 1000.0
        if not force and room <= need:
            return []
        del self.interventions[dev.id]
        if dev.kind in SETTING_KINDS:
            return [Action(dev.id, "battery_restore", None, f"{dev.name}: wieder wie vorher", False)]
        return [Action(dev.id, "script_off", None, f"{dev.name}: Eingriff zurückgenommen", False)]

    def _release(self, now: datetime, room: float, readings: dict[str, Reading]) -> list[Action]:
        if not self.interventions or _secs(self._last_release, now) < RELEASE_EVERY_S or _secs(self._last_action, now) < SETTLE_S:
            return []
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
            if dev.kind in GUARDED_KINDS and r is not None and r.soc is not None and r.soc < dev.min_soc:
                what = "Ladestand" if dev.kind == KIND_BATTERY else "Schutzwert"
                acts.append(Action(dev_id, "log", None, f"{dev.name}: {what} {r.soc:g} unter dem Mindestwert ({dev.min_soc:g})", False))
                acts += self._release_one(dev, r, 0.0, now, True)
                self._rest_until[dev_id] = now + timedelta(minutes=10)
                continue
            if dev.kind == KIND_WALLBOX or dev.max_off_min <= 0:
                continue
            since = datetime.fromisoformat(self.interventions[dev_id]["since"])
            if (now - since).total_seconds() >= dev.max_off_min * 60:
                acts.append(Action(dev_id, "log", None, f"{dev.name}: höchste Auszeit ({dev.max_off_min:.0f} min) erreicht", False))
                acts += self._release_one(dev, readings.get(dev_id) or Reading(available=False), 0.0, now, True)
                self._rest_until[dev_id] = now + timedelta(minutes=dev.max_off_min)
        return acts

    def release_all(self, now: datetime, readings: dict[str, Reading], reason: str = "") -> list[Action]:
        acts: list[Action] = []
        for dev_id in sorted(list(self.interventions), key=lambda i: -self.devices[i].priority):
            acts += self._release_one(self.devices[dev_id], readings.get(dev_id) or Reading(available=False), 99.0, now, True)
        if acts and reason:
            acts.insert(0, Action("", "log", None, f"Alles freigegeben: {reason}", False))
        for t in self._wb.values():
            t["too_little"] = t["room3"] = None
        return acts

    def forget(self) -> None:
        """Drop interventions without touching devices (they were only simulated in observe mode)."""
        self.interventions = {}
        self._wb = {}
        self._last_action = self._last_release = None
