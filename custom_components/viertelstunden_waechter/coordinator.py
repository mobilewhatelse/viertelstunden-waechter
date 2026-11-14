"""Connects the decision engine with Home Assistant: reads states, runs the engine, executes actions."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONDITION, CONF_GRID_ENERGY, CONF_GRID_INVERT, CONF_GRID_POWER, CONF_LIMIT, CONF_LOCK, CONF_MARGIN, CONF_VOLTAGE,
    CONF_NOTIFY, D_ALLOW, D_CURRENT, D_ID, D_KIND, D_NAME, D_OFF_SCRIPT, D_ON_SCRIPT, D_PHASE, D_PHASES, D_POWER, D_POWER_INVERT,
    D_RESTORE, D_SWITCH, DOMAIN, MODE_ACTIVE, MODE_OBSERVE, MODE_OFF, UPDATE_INTERVAL,
    D_BASE, D_EFFICIENCY, D_CAPACITY, D_CHARGE_MAX, D_CHARGE_MIN, D_CONNECTED, D_DEPARTURE, D_START, D_START_VALUE, D_STOP,
    D_STOP_VALUE, D_TARGET_ENTITY, D_TARGET_SOC, D_OBSERVE,
    D_COMFORT, D_MIN_SOC, D_REL1, D_REL1_VALUE, D_REL2, D_REL2_VALUE, D_RESTORE_ORIG, D_SOC, D_VALUE,
    CONF_AI_TASK, CONF_CHARGE_PLAN, CONF_MAX_AGE, CONF_OUTDOOR_TEMP, CONF_PLANNER, CONF_WEATHER, DEFAULT_MAX_AGE_S, D_RESERVE_ENTITY, D_RESERVE_LEAD, D_RESERVE_VALUE,
)
from .const import CONF_EVCC_BACKUP, CONF_EVCC_PASSWORD, CONF_EVCC_URL, D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL
from .const import D_ART, D_BATTERY_POWER, D_MAX_CURRENT
from . import geraete_check as gc
from .evcc import (SOURCES_DIFFER_AFTER_S, EvccClient, choose_grid, parse_grid_kw, parse_loadpoint, sources_differ, target_ceiling,
                   virtual_current)
from .explain import build_instructions, extract_text, plain_summary
from .messages import Messages
from .export import days_csv, quarters_csv
from .forecast import (
    MAX_PLAUSIBLE_KW, UNPLUGGED_HOUSE_ONLY_QUARTERS, LoadModel, WeatherCurve, add_running_charge, apply_car_plan, combine, quiet_until, running_charge_hours, splice, wallbox_total_w, fit_curve, parse_plan_windows, hourly, reserve_kw, reserve_window, risk_windows, weekly_profile,
)
from .corrections import correct_quarter as _correct_quarter
from . import rueckmeldung as rm
from .plan import charging_allowed, make_plan
from .pricing import monthly_cost
from .report import week_label, week_report
from .engine import (
    KIND_BATTERY, KIND_SCRIPT, KIND_SETTING, KIND_VEHICLE, KIND_SWITCH, KIND_THROTTLE, KIND_WALLBOX, STRATEGY_COMFORT, Action,
    DeviceConfig, Guard, Reading, KIND_EVCC, WALLBOX_KINDS, amps_of, percent_of, step_down,
)

_LOGGER = logging.getLogger(__name__)
_BAD = (None, "", STATE_UNKNOWN, STATE_UNAVAILABLE)


def _same_value(state: str, wanted: str) -> bool:
    """Equal as text, or as numbers (so 800 and 800.0 are the same)."""
    if state == wanted:
        return True
    try:
        return abs(float(state) - float(wanted)) < 0.5
    except ValueError:
        return False
LOG_KEEP = 200
DAYS_KEEP = 400
QUARTERS_KEEP = 120 * 96   # quarter-hour history for the export: 120 days
MODEL_VERSION = 2          # 2: the house model is filled without the wallboxes (rebuilt once from 0.14.1)
AI_CALLS_PER_DAY = 4
EXPLAIN_AT_HOUR = 21
CALL_TIMEOUT_S = 15


class Waechter:
    """One guard per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.cfg: dict[str, Any] = {**entry.data, **entry.options}
        self.raw_devices: dict[str, dict[str, Any]] = {
            sid: {**sub.data, D_ID: sid, D_KIND: sub.subentry_type, D_NAME: sub.data.get(D_NAME) or sub.title}
            for sid, sub in entry.subentries.items()
        }
        self._evcc_lp: dict[str, dict[str, Any] | None] = {}   # device id -> loadpoint as read from evcc (None = not reachable)
        self._evcc_orig: dict[str, dict[str, float]] = {}      # device id -> ceiling and virtual current when a reduction began
        self._evcc_clients: dict[tuple[str, str], EvccClient] = {}
        self._evcc_down: set[tuple[str, str]] = set()
        self.guard = Guard(
            [DeviceConfig.from_dict(self._engine_dict(d)) for d in self.raw_devices.values() if d[D_KIND] != KIND_VEHICLE], STRATEGY_COMFORT,
            float(self.cfg.get(CONF_VOLTAGE, 230.0)), hass.config.language,
        )
        self.t = Messages(hass.config.language)  # texts of the log lines and messages
        self.mode = MODE_OBSERVE
        self.limit_kw = float(self.cfg.get(CONF_LIMIT, 10.0))
        self.margin_kw = float(self.cfg.get(CONF_MARGIN, 0.5))
        self.status = "observing"
        self.executing = False
        self.log: list[dict[str, Any]] = []
        self.counts: dict[str, dict[str, int]] = {}
        self.month_peak: dict[str, Any] = {}
        self.day_peaks: dict[str, dict[str, Any]] = {}  # "2026-10-24": {"kw": 7.9, "at": "18:15"}
        self.last_quarter_kw: float | None = None
        # peak per month: {"2026-10": {"kw": actual peak, "ug": estimated peak without the guard}}
        self.months: dict[str, dict[str, float]] = {}
        # switchable features (default on) and the tariff prices
        self.paid_peak = True            # an already reached month peak above the limit raises the limit for the month
        self.notify_intervention = True  # message at the first intervention (at most every 30 minutes)
        self.predictive = False          # use the load forecast: lower the wallbox early in a risk quarter hour (default off)
        self.prewarn = False             # message before an intervention: the quarter hour heads for the limit (default off)
        self.weekly_enabled = True       # weekly report on Monday morning
        self.share_usage = bool(self.cfg.get("share_usage"))   # voluntary anonymous usage statistics, weekly (default off, rueckmeldung.py)
        self.feedback_text = ""          # the text field for a feedback
        self._usage: dict[str, Any] = {}  # {"kennung", "gesendet"}: the random id of this installation and the last report
        self._usage_busy = False
        self.weekly: dict[str, Any] = {}  # the last report
        self._prewarn_q: datetime | None = None
        self._session: list[str] = []     # what the guard did since the first intervention (for the summary message)
        self._miss_push: dict[str, datetime] = {}
        self.costs_enabled = True        # compute cost and savings
        self.price_low = 0.0             # EUR per kW and year up to the threshold
        self.price_high = 0.0            # EUR per kW and year above the threshold
        self.price_threshold = 10.0      # kW
        self._last_push: datetime | None = None
        self._battery_orig: dict[str, dict[str, str]] = {}  # settings before the release, per battery device
        # charge plan for the car
        self.plan_enabled = True         # compute the plan (needs a vehicle entry)
        self.plan_execute = False        # also carry it out (always off after a restart)
        self.plan: dict[str, Any] = {"status": "no_vehicle"}
        self._plan_at: datetime | None = None
        self._plan_paused = False        # the plan has paused the charging (and must resume it)
        self._plan_cmd_at: datetime | None = None
        self._solar_cache: tuple[datetime, dict[datetime, float] | None] | None = None
        # load forecast: learned typical grid import per weekday and quarter hour
        self.forecast_enabled = True
        self.model = LoadModel()         # house without the wallbox (all of it without a wallbox entry)
        self.wb_model = LoadModel()      # the wallbox alone
        self.forecast: dict[str, Any] = {}
        self.grid_age: float | None = None   # seconds since the grid reading was written
        self.grid_stale = False              # True: the reading is older than allowed and counts as missing
        self.grid_source: str | None = None  # "sensor" or "evcc": where the grid import of this cycle came from
        self.grid_evcc_kw: float | None = None  # what evcc reports (None = not asked or no grid meter there)
        self.sources_differ = False          # sensor and evcc differ clearly (shown, never averaged)
        self._diff_since: datetime | None = None
        self._diff_noted = False
        self._on_backup = False
        self.wallbox_twice: str | None = None   # "wallbox name / evcc name" while both seem to be the same wallbox
        self._twice_since: datetime | None = None
        self._twice_noted = False
        # weather correction of the house forecast (needs a temperature; the switch is on by default)
        self.weather_enabled = True
        self.curve = WeatherCurve()
        self.curve_info: dict[str, Any] = {"days": 0}
        self.days: dict[str, list[float]] = {}   # "YYYY-MM-DD" -> [sum kW, quarters, sum temperature, quarters with temperature]
        self._wx_hourly: dict[datetime, float] = {}  # expected outdoor temperature (deg C) per local hour
        self._wx_daily: dict[str, float] = {}        # ... per local day, when the entity has no hourly forecast
        self._wx_at: datetime | None = None
        self._wx_fetching = False
        self._curve_at: datetime | None = None
        self._days_bootstrapped = False
        self._wbq: dict[str, Any] = {"q": None, "kwh": 0.0, "t": None}  # wallbox energy of the running quarter hour
        self._wb_last: tuple[datetime, float] | None = None              # (start, kW) of the last finished quarter
        self._wb_kw_now = 0.0
        # battery reserve before a forecast peak (switch, default off)
        self.battery_reserve = False
        self._reserve: dict[str, dict[str, Any]] = {}   # battery devices held now: entity, original value, until
        self._reserve_seen: dict[str, str] = {}         # observe mode: window already logged per device
        # quarter-hour history for the export
        self.quarters: list[list[Any]] = []
        self._quarters_store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.quarters")
        # AI explainer (switch, default off and off after every restart)
        self.ai_explainer = False
        self.explanation: dict[str, Any] = {}
        self._ai_calls: dict[str, int] = {}
        self._forecast_at: datetime | None = None
        self._bootstrapped = False
        self._bootstrapping = False
        self._bootstrap_failed = False
        self._rebuild = False            # 0.14.1: fill the house model once again without the wallboxes
        # device check (0.15): says when a connected device is not right any more; nothing is switched by it
        self.check = gc.DeviceCheck(float(self.cfg.get(CONF_VOLTAGE, 230.0)))
        self._check_store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.geraete")
        self._check_busy = False
        self._check_asked = False        # the note under Repairs for those who shared before 0.15 is shown
        self._check_saved: datetime | None = None
        # the first check after a start comes 5 to 60 minutes later (spreads the requests of all installations)
        import random
        self._check_next: datetime = dt_util.now() + timedelta(minutes=random.uniform(5, 60))
        self._model_store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.model")
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._unsub = None
        self._lock = asyncio.Lock()

    @property
    def signal(self) -> str:
        return f"{DOMAIN}_{self.entry.entry_id}"

    # ---------- life cycle ----------

    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self.log = data.get("log", [])
        self.counts = data.get("counts", {})
        self.month_peak = data.get("month_peak", {})
        self.day_peaks = data.get("day_peaks", {})
        self.months = data.get("months", {})
        self.weekly = data.get("weekly", {})
        self._battery_orig = data.get("battery_orig", {})
        self._evcc_orig = data.get("evcc_orig", {})
        self._plan_paused = bool(data.get("plan_paused"))  # resumed by the first cycle (the plan switch is off)
        if self.month_peak.get("month") and self.month_peak["month"] not in self.months:
            kw = float(self.month_peak.get("kw") or 0.0)  # taken over from version 0.2
            self.months[self.month_peak["month"]] = {"kw": kw, "ug": kw}
        self.last_quarter_kw = data.get("last_quarter_kw")
        model_data = await self._model_store.async_load() or {}
        self.model = LoadModel.from_dict(model_data)
        self.wb_model = LoadModel.from_dict(model_data.get("wallbox") or {})
        self.days = {k: [float(x) for x in v] for k, v in (model_data.get("days") or {}).items() if isinstance(v, list) and len(v) == 4}
        self._days_bootstrapped = bool(model_data.get("days_bootstrapped"))
        self.quarters = (await self._quarters_store.async_load() or {}).get("rows", [])
        self.check = gc.DeviceCheck.from_dict(await self._check_store.async_load(), float(self.cfg.get(CONF_VOLTAGE, 230.0)))
        self.check.forget(set(self.raw_devices))
        self._sync_check_issues()
        self.explanation = data.get("explanation", {})
        self._ai_calls = data.get("ai_calls", {})
        self._usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
        self.ask_usage_once()
        self.check_observe_only()
        self._reserve = data.get("reserve", {})
        if self._reserve:
            await self._end_reserve_all(self.t("r_restart"))  # restarted while a battery was held: give it back first
        self._bootstrapped = bool(model_data.get("bootstrapped"))
        # 0.14.1: a house model from before took the charging of the car into the first fill; build it once again, wallboxes taken off
        if (self._bootstrapped and int(model_data.get("model_version") or 1) < MODEL_VERSION and self._has_wallbox()
                and self.cfg.get(CONF_GRID_ENERGY)):
            self._bootstrapped, self._rebuild = False, True
        if data.get("executing") and data.get("interventions"):
            # Home Assistant restarted while the guard had changed devices: give them back first
            self.guard.load({"interventions": data["interventions"]})
            await self._poll_evcc()
            await self._run(self.guard.release_all(dt_util.now(), self._readings(), self.t("r_restart")), True)
        self.guard.forget()
        self.guard.resume_quarter(data.get("quarter"))   # a reload or restart within a quarter hour continues it instead of guessing
        self._unsub = async_track_time_interval(self.hass, self._tick, UPDATE_INTERVAL)

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        async with self._lock:
            self.plan_execute = False
            await self._execute_plan(dt_util.now())  # resume a charging the plan had paused
            if self.executing and self.guard.interventions:
                await self._run(self.guard.release_all(dt_util.now(), self._readings(), self.t("r_unload")), True)
            await self._end_reserve_all(self.t("r_unload"))
            self.executing = False
            self.guard.forget()
        await self._store.async_save(self._data())
        # the quarter hours and the learned model are saved with a delay; a reload (e.g. after a change in the settings) within that
        # delay lost the last quarter hours of the export, while the last quarter-hour value (saved above) was kept
        await self._quarters_store.async_save({"rows": self.quarters})
        await self._model_store.async_save(self._model_data())
        await self._check_store.async_save(self.check.to_dict())

    async def async_set_mode(self, mode: str) -> None:
        self.mode = mode
        self.check_observe_only()
        if self._unsub is not None:
            await self._tick()

    def observe_only_names(self) -> list[str]:
        """Devices (not cars) that are set to 'observe only': the guard never acts on them, also in the mode 'active'."""
        return [d.get(D_NAME, i) for i, d in self.raw_devices.items() if d.get(D_OBSERVE) and d[D_KIND] != KIND_VEHICLE]

    def check_observe_only(self) -> None:
        """Mode 'active' but a device still on 'observe only': say so under Settings > Repairs (fixable there). Two switches with
        nearly the same name, so 'active' looked like it did not work (feedback 12.11.2026)."""
        from homeassistant.helpers import issue_registry as ir

        names = self.observe_only_names() if self.mode == MODE_ACTIVE else []
        if names:
            ir.async_create_issue(self.hass, DOMAIN, "observe_only_active", is_fixable=True, is_persistent=False,
                                  severity=ir.IssueSeverity.WARNING, translation_key="observe_only_active",
                                  translation_placeholders={"devices": ", ".join(names)})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, "observe_only_active")

    async def async_refresh(self) -> None:
        if self._unsub is not None:
            await self._tick()

    # ---------- reading states ----------

    def _state(self, eid: str | None):
        if not eid:
            return None
        st = self.hass.states.get(eid)
        return None if st is None or st.state in _BAD else st

    def _float(self, eid: str | None) -> float | None:
        st = self._state(eid)
        try:
            return float(st.state) if st else None
        except ValueError:
            return None

    def _target(self, eid: str | None) -> float | None:
        """Target state of charge from a sensor, a number or a list (select: '80' or '80%', e.g. Fordpass)."""
        st = self._state(eid)
        return percent_of(st.state) if st is not None else None

    def _wallbox_current(self, eid: str | None) -> tuple[float | None, tuple[int, ...] | None]:
        """Charging current of a wallbox and, for a list (select: '6 A', '8 A' ...), the amps it offers."""
        if not eid or eid.split(".")[0] not in ("select", "input_select"):
            return self._float(eid), None
        st = self._state(eid)
        if st is None:
            return None, None
        steps = tuple(sorted({a for a in map(amps_of, st.attributes.get("options") or []) if a is not None}))
        cur = amps_of(st.state)
        return (float(cur) if cur is not None else None), (steps or None)

    def _power_kw(self, eid: str | None, invert: bool = False) -> float | None:
        """Power in kW, the unit converted; `invert` turns the sign round (a sensor that counts import or consumption as negative)."""
        v = self._float(eid)
        if v is None:
            return None
        if invert:
            v = -v
        unit = (self.hass.states.get(eid).attributes.get("unit_of_measurement") or "W").strip()
        return v * {"W": 0.001, "kW": 1.0, "MW": 1000.0}.get(unit, 0.001)

    def _energy_kwh(self, eid: str | None) -> float | None:
        v = self._float(eid)
        if v is None:
            return None
        unit = (self.hass.states.get(eid).attributes.get("unit_of_measurement") or "kWh").strip()
        return v * {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}.get(unit, 1.0)

    def _grid_reading(self, now: datetime) -> float | None:
        """The grid import in kW, or None if it is missing or too old. A value that was not written for longer than the
        allowed age (default 2 minutes) is not a measurement any more: the guard then acts as without data (it gives
        everything back after 90 seconds) instead of steering by a stale number."""
        eid = self.cfg.get(CONF_GRID_POWER)
        grid = self._power_kw(eid, bool(self.cfg.get(CONF_GRID_INVERT))) if eid else None
        st = self._state(eid) if eid else None
        self.grid_age, self.grid_stale = None, False
        if grid is not None and st is not None:
            stamp = max(st.last_updated, getattr(st, "last_reported", st.last_updated))
            self.grid_age = round(max(0.0, (now - stamp).total_seconds()), 1)
            max_age = float(self.cfg.get(CONF_MAX_AGE, DEFAULT_MAX_AGE_S))
            if max_age > 0 and self.grid_age > max_age:
                self.grid_stale = True
                grid = None
        # the sensor the user entered wins; evcc fills the gap (no sensor entered, or reserve while the sensor has nothing usable)
        kw, source = choose_grid(grid, self.grid_evcc_kw, bool(eid), bool(self.cfg.get(CONF_EVCC_BACKUP, True)))
        self.grid_source = source
        self._watch_sources(grid, source, now)
        return kw

    def _watch_wallbox_twice(self, now: datetime, readings: dict[str, Reading]) -> None:
        """A wallbox device and an evcc loadpoint that charge at the same time with nearly the same power for two minutes are
        probably the same wallbox entered twice (two controllers on one wallbox). Say it once per episode; nothing is changed."""
        pair: tuple[str, str, float] | None = None
        for wid, wd in self.raw_devices.items():
            if wd.get(D_KIND) != KIND_WALLBOX:
                continue
            pw = (readings.get(wid) or Reading()).power_w or 0.0
            for eid, ed in self.raw_devices.items():
                if ed.get(D_KIND) != KIND_EVCC:
                    continue
                pe = (readings.get(eid) or Reading()).power_w or 0.0
                if pw > 1000 and pe > 1000 and abs(pw - pe) <= 0.15 * max(pw, pe):
                    pair = (str(wd.get(D_NAME)), str(ed.get(D_NAME)), max(pw, pe) / 1000.0)
        if pair is None:
            self._twice_since, self._twice_noted, self.wallbox_twice = None, False, None
            return
        if self._twice_since is None:
            self._twice_since = now
        elif (now - self._twice_since).total_seconds() >= SOURCES_DIFFER_AFTER_S:
            self.wallbox_twice = f"{pair[0]} / {pair[1]}"
            if not self._twice_noted:
                self._twice_noted = True
                self._log(Action("", "log", None, self.t("wb_twice", a=pair[0], b=pair[1], kw=pair[2]), False), False)

    def _watch_sources(self, sensor_kw: float | None, source: str | None, now: datetime) -> None:
        """Say it once when the reserve takes over or gives back, and once per episode when sensor and evcc differ clearly."""
        if source == "evcc" and self.cfg.get(CONF_GRID_POWER) and not self._on_backup:
            self._on_backup = True
            self._log(Action("", "log", None, self.t("grid_backup_on", b=self.grid_evcc_kw or 0.0), False), False)
        elif source == "sensor" and self._on_backup:
            self._on_backup = False
            self._log(Action("", "log", None, self.t("grid_backup_off"), False), False)
        if sources_differ(sensor_kw, self.grid_evcc_kw):
            if self._diff_since is None:
                self._diff_since = now
            elif (now - self._diff_since).total_seconds() >= SOURCES_DIFFER_AFTER_S:
                self.sources_differ = True
                if not self._diff_noted:
                    self._diff_noted = True
                    self._log(Action("", "log", None, self.t("grid_differ", a=sensor_kw or 0.0, b=self.grid_evcc_kw or 0.0), False), False)
        else:
            self._diff_since, self.sources_differ, self._diff_noted = None, False, False

    def _is_on(self, eid: str | None, unknown: bool) -> bool:
        if not eid:
            return unknown
        st = self._state(eid)
        return unknown if st is None else st.state == "on"

    # ---------- device check (0.15) ----------

    def _check_samples(self, readings: dict[str, Reading]) -> dict[str, gc.Sample]:
        """What the device check sees of every device in this cycle (from the readings the guard has anyway)."""
        out: dict[str, gc.Sample] = {}
        v = self._vehicle()
        car_soc = self._float(v.get(D_SOC)) if v else None
        for dev_id, r in readings.items():
            d = self.raw_devices.get(dev_id, {})
            kind = d.get(D_KIND)
            bw = self._power_kw(d.get(D_BATTERY_POWER)) if kind == KIND_BATTERY else None
            max_a = d.get(D_MAX_CURRENT)
            out[dev_id] = gc.Sample(
                kind=str(kind), art=d.get(D_ART) or None, power_w=r.power_w, current_a=r.current_a, phases=r.phases,
                max_current=float(max_a) if isinstance(max_a, (int, float)) else None, is_on=r.is_on,
                soc=car_soc if kind in WALLBOX_KINDS else r.soc, battery_w=bw * 1000.0 if bw is not None else None,
                intervened=self.executing and dev_id in self.guard.interventions)
        return out

    def _check_info(self) -> dict[str, dict[str, Any]]:
        """Maker and model per device, from the device registry of its power entity (for the comparison with the same devices)."""
        from homeassistant.helpers import device_registry as dr, entity_registry as er

        ents, devs = er.async_get(self.hass), dr.async_get(self.hass)
        out: dict[str, dict[str, Any]] = {}
        for dev_id, d in self.raw_devices.items():
            for key in (D_POWER, D_SWITCH, D_CURRENT, D_SOC, D_VALUE):
                e = ents.async_get(d.get(key) or "")
                dev = devs.async_get(e.device_id) if e and e.device_id else None
                if dev and (dev.manufacturer or dev.model):
                    out[dev_id] = {"hersteller": dev.manufacturer, "modell": dev.model}
                    break
        return out

    def check_devices(self) -> list[dict[str, Any]]:
        """Per device: name, status, what was found (as sentences), what is still being learned, what was measured."""
        out = []
        measured = self.check.measured()
        for dev_id, d in self.raw_devices.items():
            if d.get(D_KIND) == KIND_VEHICLE:
                continue
            r = self.check.result.get(dev_id, {}) if self.share_usage and self.check_consent() else {}
            found = [{"level": b["level"], "text": self._finding_text({"device_id": dev_id, **b})} for b in r.get("befunde", [])]
            out.append({"name": d.get(D_NAME, dev_id), "kind": d.get(D_KIND), "status": r.get("status", "none"), "found": found,
                        "learning": r.get("lernt"), "values": r.get("werte") or {}, "measured": measured.get(dev_id, {})})
        return out

    def check_state(self) -> str:
        """Sensor state: without *Share anonymous data* there is no check."""
        if not self.share_usage:
            return "sharing_off"
        return self.check.state() if self.check_consent() else "confirm"

    def _ask_check_consent(self) -> None:
        """Shared already before 0.15: one quiet note under Repairs (no message, no pop-up). Until it is confirmed the usage
        statistics go on as before, but no measured values are sent for the device check."""
        from homeassistant.helpers import issue_registry as ir

        want = self.share_usage and not self.check_consent()
        if want == self._check_asked:
            return
        self._check_asked = want
        if want:
            ir.async_create_issue(self.hass, DOMAIN, "share_usage_check", is_fixable=True, is_persistent=False,
                                  severity=ir.IssueSeverity.WARNING, translation_key="share_usage_check")
        else:
            ir.async_delete_issue(self.hass, DOMAIN, "share_usage_check")

    async def _check_step(self, now: datetime, readings: dict[str, Reading]) -> None:
        try:
            self.check.step(now, self._check_samples(readings), self._temp_at(now))
        except Exception:  # noqa: BLE001 - the device check must never stop the guard
            _LOGGER.exception("Device check: measuring failed")
            return
        if self._check_saved is None or now - self._check_saved > timedelta(minutes=10):
            self._check_saved = now
            self._check_store.async_delay_save(self.check.to_dict, 5)
        self._ask_check_consent()
        if not self.share_usage or not self.check_consent():
            if self.check.result:   # switched off: no check any more, findings and repairs go away
                self.check.clear()
                self._sync_check_issues()
                async_dispatcher_send(self.hass, self.signal)
            return
        last = None
        try:
            last = datetime.fromisoformat(self.check.checked_at) if self.check.checked_at else None
        except ValueError:
            pass
        due = last is None or now - last >= timedelta(hours=gc.CHECK_EVERY_H)
        if due and now >= self._check_next and not self._check_busy:
            self._check_busy = True
            self._check_next = now + timedelta(hours=gc.RETRY_H)
            self.entry.async_create_background_task(self.hass, self._check_send(now), f"{DOMAIN} device check")

    async def _check_send(self, now: datetime) -> None:
        try:
            v, _ = self._version()
            body = self.check.request(now, self._check_info(), v)
            async with asyncio.timeout(15):
                async with async_get_clientsession(self.hass).post(
                        gc.SERVICE_URL, json=body, headers={"User-Agent": f"{DOMAIN}/{v}"}) as r:
                    if r.status != 200:
                        _LOGGER.debug("Device check: service answered %s", r.status)
                        return
                    answer = await r.json(content_type=None)
            before = set(self.check.findings())
            self.check.apply(now, answer)
            await self._check_store.async_save(self.check.to_dict())
            await self._announce_findings(before)
            self._sync_check_issues()
            async_dispatcher_send(self.hass, self.signal)
        except Exception as err:  # noqa: BLE001 - not reachable: the last result stays, the next try in some hours
            _LOGGER.debug("Device check not done: %s", err)
        finally:
            self._check_busy = False

    def _finding_text(self, f: dict[str, Any]) -> str:
        name = self.raw_devices.get(f["device_id"], {}).get(D_NAME, f["device_id"])
        return gc.text(self.hass.config.language, f["key"], str(name), f.get("werte") or {})

    async def _announce_findings(self, before: set[str]) -> None:
        """A new finding is written to the log; a new warning also goes out as a message (if messages are set up)."""
        for k, f in self.check.findings().items():
            if k in before:
                continue
            txt = ("⚠ " if f["level"] == "warn" else "") + self._finding_text(f)
            self._log(Action("", "log", None, txt, False), False)
            if f["level"] == "warn" and self.notify_intervention:
                await self._exec(Action("", "notify", None, txt))

    def _sync_check_issues(self) -> None:
        """One repair per warning (with "ignore"); repairs of findings that ended are removed."""
        from homeassistant.helpers import issue_registry as ir

        prefix = f"device_check_{self.entry.entry_id}_"
        want = {}
        for k, f in self.check.findings().items():
            if f["level"] == "warn":
                want[prefix + k.replace(":", "_")] = f
        for (domain, issue_id) in list(ir.async_get(self.hass).issues):
            if domain == DOMAIN and issue_id.startswith(prefix) and issue_id not in want:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        for issue_id, f in want.items():
            name = self.raw_devices.get(f["device_id"], {}).get(D_NAME, f["device_id"])
            ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=False, is_persistent=False, severity=ir.IssueSeverity.WARNING,
                                  translation_key="device_check", translation_placeholders={"name": str(name), "detail": self._finding_text(f)})

    def _readings(self) -> dict[str, Reading]:
        out: dict[str, Reading] = {}
        for dev_id, d in self.raw_devices.items():
            if d[D_KIND] == KIND_VEHICLE:
                continue
            r = Reading(allowed=self._is_on(d.get(D_ALLOW), False) if d.get(D_ALLOW) else True)
            p = self._power_kw(d.get(D_POWER), bool(d.get(D_POWER_INVERT)))
            r.power_w = p * 1000.0 if p is not None else None
            kind = d[D_KIND]
            if kind == KIND_EVCC:
                lp = self._evcc_lp.get(dev_id)
                if p is None and lp:
                    r.power_w = lp["power_w"]
                r.current_a = virtual_current(lp)
                r.available = r.current_a is not None
                if lp:
                    r.phases = lp["phases_active"]
                    if d.get(D_EVCC_ONE_PHASE) and lp["phases_switchable"] and lp["phases_configured"] is not None:
                        r.phase_option = str(lp["phases_configured"])
            elif kind == KIND_WALLBOX:
                r.current_a, r.current_steps = self._wallbox_current(d.get(D_CURRENT))
                r.available = r.current_a is not None
                st = self._state(d.get(D_PHASE))
                r.phase_option = st.state if st else None
                ph = self._float(d.get(D_PHASES))
                r.phases = int(ph) if ph is not None else None
            elif kind == KIND_SWITCH:
                st = self._state(d.get(D_SWITCH))
                r.available = st is not None
                r.is_on = st is not None and st.state == "on"
                r.restore_allowed = self._is_on(d.get(D_RESTORE), False) if d.get(D_RESTORE) else True
            elif kind == KIND_SCRIPT:
                r.available = self.hass.states.get(d.get(D_ON_SCRIPT) or "") is not None
            elif kind == KIND_THROTTLE:
                r.value = self._float(d.get(D_VALUE))
                r.available = r.value is not None
                r.soc = self._float(d.get(D_COMFORT))
            elif kind in (KIND_BATTERY, KIND_SETTING):
                r.soc = self._float(d.get(D_SOC) or d.get(D_COMFORT))
                pairs = self._battery_pairs(d)
                r.available = any(self._state(e) is not None for e, _ in pairs)
                r.releasable = any(self._state(e) is not None and not _same_value(self._state(e).state, v) for e, v in pairs)
            out[dev_id] = r
        return out

    # ---------- main cycle ----------

    async def _tick(self, _now: datetime | None = None) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            now = dt_util.now()
            await self._poll_evcc()
            readings = self._readings()
            locked = self._is_on(self.cfg.get(CONF_LOCK), False)
            execute = self.mode == MODE_ACTIVE and not locked
            if execute != self.executing:
                if self.executing:  # leaving active mode: give back what was really changed
                    await self._run(self.guard.release_all(now, readings, self.t("r_mode")), True)
                self.guard.forget()  # interventions seen in observe mode never happened
                self.executing = execute
            self._wb_accumulate(now, readings)
            self._watch_wallbox_twice(now, readings)
            await self._check_step(now, readings)
            needed = self._is_on(self.cfg.get(CONF_CONDITION), True)
            grid = self._grid_reading(now)
            self.guard.real_effect = execute
            reserve, info = 0.0, None
            if self.predictive and self.forecast_enabled and self.mode != MODE_OFF:
                reserve, info = reserve_kw(self._view_now(), now, self.effective_limit(now) - self.margin_kw,
                                           temp=self._temp_at(now), curve=self.curve if self.weather_enabled else None)
            acts = self.guard.step(
                now,
                max(0.0, grid) if grid is not None else None,
                self._energy_kwh(self.cfg.get(CONF_GRID_ENERGY)),
                readings,
                self.effective_limit(now),
                self.margin_kw,
                self.mode != MODE_OFF and needed,
                reserve,
                self.t("why_forecast", high=info["high"], typ=info["typical"]) if info else "",
            )
            await self._run(acts, execute)
            if execute:
                await self._push_intervention(acts, now)
            await self._prewarning(now, needed)
            await self._weekly_due(now)
            self._usage_step(now)
            if self.guard.finished_quarter_kw is not None and self.guard.finished_estimated:
                self.last_quarter_kw = None   # began with a guess (the guard started in its middle): no peak, nothing learned
            elif self.guard.finished_quarter_kw is not None:
                self._quarter_done(self.guard.finished_quarter_kw, self.guard.finished_unguarded_kw, now)
            self._maybe_bootstrap()
            self._update_forecast(now)
            await self._update_plan(now)
            await self._execute_plan(now)
            await self._battery_reserve_step(now, execute)
            await self._explain_due(now)
            self.status = self._status(locked, needed)
            self._store.async_delay_save(self._data, 10)
        async_dispatcher_send(self.hass, self.signal)

    def _status(self, locked: bool, needed: bool) -> str:
        if self.mode == MODE_OFF:
            return "off"
        if self.guard.state == "no_data":
            return "no_data"
        if self.mode == MODE_ACTIVE and locked:
            return "locked"
        if not needed:
            return "idle"
        if self.mode == MODE_OBSERVE:
            return "would_intervene" if self.guard.interventions else "observing"
        return "intervening" if self.guard.interventions else "ready"

    def effective_limit(self, now: datetime) -> float:
        """The limit the guard works with. With "use paid peak" a month peak above the limit raises it for the rest
        of the month: quarter hours below the peak that was already reached cost nothing extra."""
        if not self.paid_peak:
            return self.limit_kw
        reached = float(self.months.get(now.strftime("%Y-%m"), {}).get("kw") or 0.0)
        return max(self.limit_kw, reached)

    def cost(self, peak_kw: float) -> float:
        return monthly_cost(peak_kw, self.price_low, self.price_high, self.price_threshold)

    @property
    def prices_set(self) -> bool:
        return self.price_low > 0 or self.price_high > 0

    def month_costs(self, month: str) -> dict[str, float | None]:
        """Cost with the guard, without it (estimate) and the difference for one month."""
        m = self.months.get(month)
        if not m or not self.costs_enabled or not self.prices_set:
            return {"peak": m.get("kw") if m else None, "peak_without": m.get("ug") if m else None,
                    "cost": None, "cost_without": None, "saving": None}
        ug = max(float(m.get("ug") or 0.0), float(m["kw"]))
        cost, without = self.cost(float(m["kw"])), self.cost(ug)
        return {"peak": float(m["kw"]), "peak_without": ug, "cost": round(cost, 2),
                "cost_without": round(without, 2), "saving": round(max(0.0, without - cost), 2)}

    def year_saving(self, year: str) -> float | None:
        if not self.costs_enabled or not self.prices_set:
            return None
        return round(sum(self.month_costs(m)["saving"] or 0.0 for m in self.months if m.startswith(year)), 2)

    async def _push_intervention(self, acts: list[Action], now: datetime) -> None:
        """Messages about what the guard did: one at the first intervention (all steps of that cycle, at most every
        30 minutes) and a summary of everything it did when it has given everything back."""
        if not self.notify_intervention:
            self._session = []
            return
        shown = ("set_current", "set_phase", "turn_off", "turn_on", "script_on", "script_off", "battery_release",
                 "battery_restore", "set_value")
        done = [a for a in acts if a.text and a.kind in shown]
        reductions = [a for a in done if a.intervention]
        if self._session or reductions:
            self._session += [f"{now:%H:%M:%S} {a.text}" for a in done]
        if reductions and (self._last_push is None or (now - self._last_push) >= timedelta(minutes=30)):
            self._last_push = now
            await self._exec(Action("", "notify", None, self.t("push_iv", text="; ".join(a.text for a in reductions))))
        if self._session and not self.guard.interventions:
            lines = self._session[:15] + ([f"... (+{len(self._session) - 15})"] if len(self._session) > 15 else [])
            await self._exec(Action("", "notify", None, self.t("push_done") + "\n" + "\n".join(lines)))
            self._session = []

    async def _prewarning(self, now: datetime, needed: bool) -> None:
        """Optional message before an intervention: once per quarter hour when the forecast of the running quarter
        reaches 90 % of the limit and the guard has not intervened yet (an intervention sends its own message)."""
        v = self.guard.values
        if not self.prewarn or self.mode == MODE_OFF or not needed or self.guard.state == "no_data":
            return
        fc, limit = v.get("forecast_kw"), v.get("limit_kw")
        q = v.get("quarter")
        if fc is None or not limit or q is None or self._prewarn_q == q or self.guard.interventions:
            return
        if fc >= 0.9 * float(limit):
            self._prewarn_q = q
            await self._exec(Action("", "notify", None,
                                    self.t("prewarn", fc=fc, limit=float(limit), now=float(v.get("grid_kw") or 0.0))))

    def build_week(self, start, days: int = 7) -> dict[str, Any]:
        month = (start + timedelta(days=days - 1)).strftime("%Y-%m")
        mp = self.months.get(month, {}).get("kw")
        return week_report(self.day_peaks, self.counts, self.limit_kw, start, days, float(mp) if mp else None,
                           self.month_costs(month) if mp else None, self.hass.config.language)

    async def send_week_report(self, current: bool = False, push: bool = True) -> dict[str, Any]:
        """The last full week (Mon-Sun), or with `current` the running week so far."""
        today = dt_util.now().date()
        monday = today - timedelta(days=today.weekday())
        rep = self.build_week(monday if current else monday - timedelta(days=7), today.weekday() + 1 if current else 7)
        self.weekly = {**rep, "sent": dt_util.now().isoformat(timespec="seconds"), "partial": current}
        self._store.async_delay_save(self._data, 5)
        if push:
            await self._exec(Action("", "notify", None, rep["text"]))
        async_dispatcher_send(self.hass, self.signal)
        return rep

    async def _weekly_due(self, now: datetime) -> None:
        """Monday from 07:00: report the week that ended yesterday, once."""
        if not self.weekly_enabled or now.weekday() != 0 or now.hour < 7:
            return
        last_week = (now - timedelta(days=7)).date()
        label = week_label(last_week)
        if self.weekly.get("week") == label and not self.weekly.get("partial"):
            return
        rep = self.build_week(now.date() - timedelta(days=7))
        if rep["days_with_data"] == 0:
            self.weekly = {**rep, "sent": None, "partial": False}  # nothing to report (fresh installation)
            return
        await self.send_week_report(False, True)

    def _quarter_done(self, kw: float, unguarded_kw: float | None, now: datetime) -> None:
        self.last_quarter_kw = kw
        start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0) - timedelta(minutes=15)
        month = start.strftime("%Y-%m")
        m = self.months.setdefault(month, {"kw": 0.0, "ug": 0.0})
        m["kw"] = max(float(m.get("kw") or 0.0), kw)
        m["ug"] = max(float(m.get("ug") or 0.0), kw, unguarded_kw or 0.0)
        for k in sorted(self.months)[:-15]:
            del self.months[k]
        total = unguarded_kw if unguarded_kw is not None else kw
        wb_kw = self._wb_last[1] if self._wb_last is not None and self._wb_last[0] == start else None
        if self.forecast_enabled:  # learn what the load would be without the guard
            temp = self._temp_now() if self.weather_enabled else None
            if self._has_wallbox() and wb_kw is not None:
                house = max(0.0, kw - wb_kw)          # measured import minus measured wallbox
                self.model.add(start, house, temp)
                self.wb_model.add(start, max(0.0, total - house))  # the wallbox, including what the guard held back
                self._day_add(start, house, temp)
            else:
                self.model.add(start, total, temp)
                self._day_add(start, total, temp)
            self._model_store.async_delay_save(self._model_data, 120)
        self.quarters.append([start.isoformat(timespec="minutes"), round(kw, 3),
                              round(total, 3), round(wb_kw, 3) if wb_kw is not None else None])
        del self.quarters[:-QUARTERS_KEEP]
        self._quarters_store.async_delay_save(lambda: {"rows": self.quarters}, 300)
        if self.month_peak.get("month") != month or kw > float(self.month_peak.get("kw") or 0.0):
            self.month_peak = {"month": month, "kw": kw, "at": start.isoformat()}
        day = start.strftime("%Y-%m-%d")
        if kw > float(self.day_peaks.get(day, {}).get("kw") or 0.0):
            self.day_peaks[day] = {"kw": kw, "at": start.strftime("%H:%M")}
        for k in sorted(self.day_peaks)[:-DAYS_KEEP]:
            del self.day_peaks[k]

    # ---------- load forecast ----------

    def _model_data(self) -> dict[str, Any]:
        return {**self.model.to_dict(), "wallbox": self.wb_model.to_dict(), "bootstrapped": self._bootstrapped,
                "model_version": 1 if self._rebuild else MODEL_VERSION,
                "days": {k: [round(x, 3) for x in v] for k, v in self.days.items()}, "days_bootstrapped": self._days_bootstrapped}

    # ---------- weather correction ----------

    @staticmethod
    def _to_celsius(value: float | None, unit: str | None) -> float | None:
        if value is None:
            return None
        u = (unit or "").replace("\u00b0", "").strip().upper()
        c = (value - 32.0) * 5.0 / 9.0 if u == "F" else value - 273.15 if u == "K" else value
        return round(c, 1) if -60.0 <= c <= 60.0 else None

    def _temp_of(self, eid: str | None) -> float | None:
        st = self._state(eid)
        if st is None:
            return None
        try:
            if eid and eid.startswith("weather."):
                return self._to_celsius(float(st.attributes.get("temperature")), st.attributes.get("temperature_unit"))
            return self._to_celsius(float(st.state), st.attributes.get("unit_of_measurement"))
        except (TypeError, ValueError):
            return None

    def _temp_now(self) -> float | None:
        """Outdoor temperature now: the sensor if there is one, else the weather entity."""
        t = self._temp_of(self.cfg.get(CONF_OUTDOOR_TEMP))
        return t if t is not None else self._temp_of(self.cfg.get(CONF_WEATHER))

    def _temp_at(self, when: datetime) -> float | None:
        """Expected outdoor temperature (deg C) in the quarter hour `when`, None if the forecast does not reach it."""
        if not self.weather_enabled:
            return None
        v = self._wx_hourly.get(when.replace(minute=0, second=0, microsecond=0))
        return v if v is not None else self._wx_daily.get(when.strftime("%Y-%m-%d"))

    def _wx_args(self) -> dict[str, Any]:
        """Keyword arguments for `LoadModel.horizon` / `reserve_kw`: empty = no correction (no switch, no curve)."""
        if not self.weather_enabled or not self.curve.active:
            return {}
        return {"temp_at": self._temp_at, "curve": self.curve}

    def _day_add(self, start: datetime, kw: float, temp: float | None) -> None:
        d = self.days.setdefault(start.strftime("%Y-%m-%d"), [0.0, 0, 0.0, 0])
        d[0] += kw
        d[1] += 1
        if temp is not None:
            d[2] += temp
            d[3] += 1
        for k in sorted(self.days)[:-150]:
            del self.days[k]

    def _refit_curve(self, now: datetime) -> None:
        if self._curve_at is not None and (now - self._curve_at) < timedelta(hours=1):
            return
        self._curve_at = now
        today = now.strftime("%Y-%m-%d")
        rows = []
        for k, v in self.days.items():
            if k != today and v[1] >= 80 and v[3] >= 80:  # whole days with load and temperature
                rows.append((datetime.strptime(k, "%Y-%m-%d").weekday(), v[0] / v[1], v[2] / v[3]))
        self.curve, self.curve_info = fit_curve(rows)

    def _maybe_fetch_weather(self, now: datetime) -> None:
        eid = self.cfg.get(CONF_WEATHER)
        if not eid or not self.weather_enabled or self._wx_fetching:
            return
        if self._wx_at is not None and (now - self._wx_at) < timedelta(minutes=30):
            return
        self._wx_fetching = True
        self.entry.async_create_background_task(self.hass, self._fetch_weather(eid), f"{DOMAIN} weather")

    async def _fetch_weather(self, eid: str) -> None:
        try:
            st = self.hass.states.get(eid)
            unit = st.attributes.get("temperature_unit") if st else None
            for kind in ("hourly", "daily"):
                try:
                    resp = await self.hass.services.async_call(
                        "weather", "get_forecasts", {"entity_id": eid, "type": kind}, blocking=True, return_response=True)
                except Exception:  # noqa: BLE001 - this weather entity may not offer this kind
                    continue
                rows = ((resp or {}).get(eid) or {}).get("forecast") or []
                hours: dict[datetime, float] = {}
                days: dict[str, float] = {}
                for row in rows:
                    when = dt_util.parse_datetime(str(row.get("datetime")))
                    temp = row.get("temperature")
                    if when is None or temp is None:
                        continue
                    when = dt_util.as_local(when)
                    if kind == "hourly":
                        t = self._to_celsius(float(temp), unit)
                        if t is not None:
                            hours[when.replace(minute=0, second=0, microsecond=0)] = t
                    else:
                        low = row.get("templow")
                        mean = (float(temp) + float(low)) / 2.0 if low is not None else float(temp)
                        t = self._to_celsius(mean, unit)
                        if t is not None:
                            days[when.strftime("%Y-%m-%d")] = t
                if hours or days:
                    self._wx_hourly, self._wx_daily = hours, days
                    break
        except Exception as err:  # noqa: BLE001 - the weather is optional, the guard must not depend on it
            _LOGGER.debug("Weather forecast not available: %s", err)
        finally:
            self._wx_at = dt_util.now()
            self._wx_fetching = False
            self._forecast_at = None

    def _update_forecast(self, now: datetime) -> None:
        if not self.forecast_enabled:
            self.forecast = {}
            return
        if self._forecast_at is not None and (now - self._forecast_at) < timedelta(minutes=5):
            return
        self._forecast_at = now
        target = float(self.guard.values.get("target_kw") or (self.limit_kw - self.margin_kw))
        car = self._car_may_charge()
        unplugged = not car and self._car_unplugged()
        view = self._view_all() if car or unplugged else self.model
        self._refit_curve(now)
        self._maybe_fetch_weather(now)
        series = view.horizon(now, 24, **self._wx_args())
        if unplugged:   # not plugged in: cannot charge in the next hour, but may well be plugged in later today (the learned pattern)
            series = splice(self.model.horizon(now, 24, **self._wx_args()), series, UNPLUGGED_HOUSE_ONLY_QUARTERS)
        plan = self._car_plan(now)
        if plan is not None:  # a charge plan that is executed says when the car really charges: it replaces the learned wallbox
            # pattern until departure. A plan nobody executes (learn mode) only adds to the usual view, it never lowers it.
            series = apply_car_plan(self.model.horizon(now, 24, **self._wx_args()), series, plan[0], plan[1], plan[2])
        running = self._running_charge(now)
        if running is not None:   # a charge that runs now is in the forecast until its probable end, whatever was learned
            series = add_running_charge(self.model.horizon(now, 24, **self._wx_args()), series, running[0], running[1])
        highs = [q["high"] for q in series if q["high"] is not None]
        self.forecast = {
            "target": target,
            "now": series[0],
            "peak": max(highs) if highs else None,
            "windows": risk_windows(series, target),
            "hours": hourly(series),
            # the house alone (no wallbox, no running charge, no car plan): for a charge planner such as Plugwhen, which must not
            # count the car it plans as load in its own way
            "hours_house": hourly(self.model.horizon(now, 24, **self._wx_args())),
            "profile": weekly_profile(self._view_all()),
            "vehicle_included": car or (unplugged and "after_1h"),
            "car_plan": {
                "configured": len(self._plan_entities()),
                "used": plan is not None,
                "windows": len(plan[0]) if plan else 0,
                "until": plan[1].isoformat() if plan else None,
                "executed": plan[2] if plan else None,
            },
            "running_charge": {"kw": round(running[0], 2), "until": running[1].isoformat()} if running else None,
            "weather": {
                "enabled": self.weather_enabled,
                "configured": bool(self.cfg.get(CONF_WEATHER) or self.cfg.get(CONF_OUTDOOR_TEMP)),
                "active": bool(self._wx_args()) and any(self._temp_at(q["t"]) is not None for q in series),
                "temperature_now": self._temp_now(),
                "heat_kw_per_k": self.curve.heat_kw_per_k,
                "cool_kw_per_k": self.curve.cool_kw_per_k,
                "days": self.curve_info.get("days", 0),
                "days_recorded": len(self.days),
                "days_from_history": self._days_bootstrapped,
                "r2": self.curve_info.get("r2", 0.0),
                "forecast_hours": len(self._wx_hourly) or len(self._wx_daily) * 24,
            },
            "samples": self.model.samples,
            "slots": self.model.slots_with_data,
        }

    def _running_charge(self, now: datetime) -> tuple[float, datetime] | None:
        """(power in kW, probable end) of a charge that runs right now, or None. The end comes from the vehicle entry (state of
        charge up to the car's own limit, capacity); without one a usual duration is assumed."""
        p = self._wb_kw_now
        if p < 1.0:
            return None
        v = self._vehicle() or {}
        limit = self._target(v.get(D_TARGET_ENTITY))
        hours = running_charge_hours(p, self._float(v.get(D_SOC)), limit, v.get(D_CAPACITY), v.get(D_EFFICIENCY))
        return (p, now + timedelta(hours=hours)) if hours > 0 else None

    async def correct_quarter(self, start: str, kw: float) -> dict[str, Any]:
        """A quarter hour recorded wrong gets the value from the meter; the day's and the month's peak are worked out again and
        written to the log (service correct_quarter)."""
        result = _correct_quarter(self.quarters, self.day_peaks, self.months, self.month_peak, start, kw)
        if self.last_quarter_kw is not None and abs(float(self.last_quarter_kw) - result["old_kw"]) < 1e-3:
            self.last_quarter_kw = result["new_kw"]
        self._log(Action("", "log", None, self.t("corrected", start=result["start"][:16].replace("T", " "), old=result["old_kw"],
                                                  new=result["new_kw"]), False), False)
        await self._store.async_save(self._data())
        await self._quarters_store.async_save({"rows": self.quarters})
        async_dispatcher_send(self.hass, self.signal)
        return result

    # ---------- voluntary usage statistics and feedback (rueckmeldung.py) ----------

    def setup_overview(self) -> dict[str, Any]:
        """What is set up, without names, entity ids or values: kinds of devices and the integrations their entities come from."""
        from homeassistant.helpers import entity_registry as er

        reg = er.async_get(self.hass)
        kinds: dict[str, int] = {}
        ids: list[str] = [x for x in (self.cfg.get(CONF_GRID_POWER), self.cfg.get(CONF_GRID_ENERGY)) if x]
        for d in self.raw_devices.values():
            kinds[d[D_KIND]] = kinds.get(d[D_KIND], 0) + 1
            ids += [v for k, v in d.items() if str(k).endswith("_entity") and isinstance(v, str)]

        def platform(eid: str) -> str | None:
            ent = reg.async_get(eid)
            return ent.platform if ent else None

        return {
            "geraete": kinds,
            "herkunft": rm.herkunft(ids, platform),
            "nur_beobachten": sum(1 for d in self.raw_devices.values() if d.get("observe_only")),
            "netzbezug": "beide" if self.cfg.get(CONF_GRID_POWER) and self.cfg.get(CONF_EVCC_URL)
                         else "evcc" if self.cfg.get(CONF_EVCC_URL) else "sensor",
            "vorzeichen_umgekehrt": bool(self.cfg.get(CONF_GRID_INVERT)),
            "betriebsart": self.mode,
            "planer": bool(self.cfg.get(CONF_PLANNER) or self.cfg.get(CONF_CHARGE_PLAN)),
            "prognose": bool(self.forecast_enabled), "wetter": bool(self.weather_enabled), "vorausschauend": bool(self.predictive),
        }

    def _version(self) -> tuple[str, str]:
        from homeassistant.const import __version__ as ha_version
        from homeassistant.loader import async_get_loaded_integration

        try:
            v = str(async_get_loaded_integration(self.hass, DOMAIN).version or "?")
        except Exception:  # noqa: BLE001
            v = "?"
        return v, ha_version

    def ask_usage_once(self) -> None:
        """An installation from before the question (set up without the last step of the assistant): ask once, in Settings >
        Repairs. Not again after an answer or after "ignore"."""
        from homeassistant.helpers import issue_registry as ir

        if "share_usage" in self.entry.options:
            self._usage["gefragt"] = True   # answered in the set-up; a later change of the settings must not ask again
            return
        if self._usage.get("gefragt") or self.share_usage:
            return
        ir.async_create_issue(self.hass, DOMAIN, "share_usage_question", is_fixable=True, is_persistent=False,
                              severity=ir.IssueSeverity.WARNING, translation_key="share_usage_question")

    def check_consent(self) -> bool:
        """Was the consent given with the text of 0.15 (the device check sends measured values)? Set up or asked from 0.15 on,
        the switch turned on from 0.15 on, or the note under Repairs confirmed."""
        return bool(self._usage.get("check_ok") or self.entry.options.get("share_check"))

    def confirm_check(self, share: bool) -> None:
        """Answer to the note under Repairs: keep sharing (with the device check) or switch sharing off."""
        if share:
            self._usage["check_ok"] = True
            self._store.async_delay_save(self._data, 1)
            async_dispatcher_send(self.hass, self.signal)
        else:
            self.answer_usage(False)

    def answer_usage(self, share: bool) -> None:
        self.share_usage = bool(share)
        self._usage["gefragt"] = True
        if share:
            self._usage["check_ok"] = True   # the question of 0.15 describes the device check
        self._store.async_delay_save(self._data, 1)
        from homeassistant.helpers.dispatcher import async_dispatcher_send

        async_dispatcher_send(self.hass, self.signal)

    def _usage_step(self, now: datetime) -> None:
        """Weekly while the switch is on; once 'delete' after it was switched off. Runs in the background, never blocks."""
        if self._usage_busy:
            return
        if self.share_usage and rm.faellig(self._usage.get("gesendet"), now):
            if not self._usage.get("kennung"):
                self._usage["kennung"] = rm.neue_kennung()
            v, ha = self._version()
            daten = rm.statistik(DOMAIN, v, ha, self._usage["kennung"], self.hass.config.country, self.hass.config.language,
                                 self.setup_overview())
        elif not self.share_usage and self._usage.get("kennung"):
            daten = rm.loeschen(DOMAIN, self._usage["kennung"])
        else:
            return
        self._usage_busy = True
        self.entry.async_create_background_task(self.hass, self._usage_send(daten, now), f"{DOMAIN} usage")

    async def _usage_send(self, daten: dict[str, Any], now: datetime) -> None:
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        try:
            ok = await rm.senden(async_get_clientsession(self.hass), rm.ZIEL_STATISTIK, daten)
            if daten.get("loeschen"):
                if ok:
                    self._usage = {"gefragt": True} if self._usage.get("gefragt") else {}
            else:
                # sent or not: the next try comes in a week, never every cycle (an unreachable server must not cause traffic)
                self._usage["gesendet"] = now.isoformat()
            self._store.async_delay_save(self._data, 5)
        finally:
            self._usage_busy = False

    async def send_feedback(self, text: str, kontakt: str | None, mit_einrichtung: bool) -> bool:
        """A feedback the user writes and sends himself (service send_feedback, or the text field and its button)."""
        from homeassistant.helpers.aiohttp_client import async_get_clientsession

        if not str(text or "").strip():
            return False
        v, ha = self._version()
        daten = rm.rueckmeldung(DOMAIN, v, ha, text, kontakt, self.setup_overview() if mit_einrichtung else None)
        return await rm.senden(async_get_clientsession(self.hass), rm.ZIEL_RUECKMELDUNG, daten)

    def _plan_entities(self) -> list[str]:
        """Charge plan sensors: those of the chosen car planner (all vehicles, found by their unique id) plus entities named by hand."""
        v = self.cfg.get(CONF_CHARGE_PLAN) or []
        found = [x for x in ([v] if isinstance(v, str) else list(v)) if x]
        entry_id = self.cfg.get(CONF_PLANNER)
        if entry_id:
            from homeassistant.helpers import entity_registry as er

            found += sorted(e.entity_id for e in er.async_entries_for_config_entry(er.async_get(self.hass), entry_id)
                            if e.domain == "sensor" and str(e.unique_id).endswith("_charge_plan"))
        return list(dict.fromkeys(found))

    def _car_plan(self, now: datetime) -> tuple[list[dict[str, Any]], datetime, bool] | None:
        """Planned car load from the charge plan sensors (optional): `(windows, last departure, executed)` or None if no
        plan is configured or usable (then the forecast works as before). A plan counts while its state is planned,
        not_needed or infeasible and its departure is ahead; several cars add up. `executed` is False as soon as one plan
        says with its attribute `executed: false` that nobody switches the wallbox by it (a missing attribute counts as
        executed, as before)."""
        windows: list[dict[str, Any]] = []
        until: datetime | None = None
        executed = True
        for eid in self._plan_entities():
            st = self.hass.states.get(eid)
            if st is None or st.state not in ("planned", "not_needed", "infeasible"):
                continue
            dep = dt_util.parse_datetime(str(st.attributes.get("departure") or ""))
            if dep is None or dep <= now:
                continue
            windows += parse_plan_windows(st.attributes.get("windows"), now.tzinfo)
            if st.attributes.get("executed") is False:
                executed = False
            else:   # an executed plan: nothing is charged before the planner's next need, so it covers the car until then
                dep = quiet_until(st.attributes.get("horizon"), dep, now, now.tzinfo)
            until = dep if until is None or dep > until else until
        return (windows, until, executed) if until is not None else None

    def _maybe_bootstrap(self) -> None:
        """Once: fill the model from the hourly statistics of the grid import counter (lower bounds). With an outdoor
        temperature sensor the temperatures of that time and the daily records for the weather curve come along; an
        installation that was filled before gets only the daily records."""
        if (not self.forecast_enabled or self._bootstrapping or self._bootstrap_failed
                or not self.cfg.get(CONF_GRID_ENERGY)):
            return
        need_days = not self._days_bootstrapped and self.weather_enabled and bool(self.cfg.get(CONF_OUTDOOR_TEMP))
        if self._bootstrapped and not need_days:
            return
        self._bootstrapping = True
        self.entry.async_create_background_task(self.hass, self._bootstrap(not self._bootstrapped, need_days),
                                                f"{DOMAIN} history")

    async def _bootstrap(self, need_model: bool = True, need_days: bool = False) -> None:
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            eid = self.cfg[CONF_GRID_ENERGY]
            st = self.hass.states.get(eid)
            unit = ((st.attributes.get("unit_of_measurement") if st else None) or "kWh").strip()
            factor = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}.get(unit, 1.0)
            end = dt_util.now()
            start = end - timedelta(days=84)
            recorder = get_instance(self.hass)
            stats = await recorder.async_add_executor_job(
                statistics_during_period, self.hass, start, end, {eid}, "hour", None, {"change"}
            )
            # the wallboxes are taken off the grid import hour by hour (their mean power), so that the house model does not learn
            # the charging of the car as house load; without a power sensor with statistics nothing can be taken off
            wb_hour: dict[float, float] = {}
            wb_src: dict[str, tuple[float, float]] = {}
            for d in self.raw_devices.values():
                pid = d.get(D_POWER)
                if d.get(D_KIND) in WALLBOX_KINDS and pid and pid not in wb_src:
                    pst = self.hass.states.get(pid)
                    punit = ((pst.attributes.get("unit_of_measurement") if pst else None) or "W").strip()
                    wb_src[pid] = ({"W": 0.001, "kW": 1.0, "MW": 1000.0}.get(punit, 0.001), -1.0 if d.get(D_POWER_INVERT) else 1.0)
            if wb_src:
                wstats = await recorder.async_add_executor_job(
                    statistics_during_period, self.hass, start, end, set(wb_src), "hour", None, {"mean"}
                )
                for pid, (pf, sign) in wb_src.items():
                    for row in wstats.get(pid, []):
                        if row.get("mean") is not None:
                            wb_hour[row["start"]] = wb_hour.get(row["start"], 0.0) + max(0.0, sign * float(row["mean"]) * pf)
            temps: dict[float, float | None] = {}
            outdoor = self.cfg.get(CONF_OUTDOOR_TEMP)
            if outdoor and self.weather_enabled:
                tst = self.hass.states.get(outdoor)
                tunit = tst.attributes.get("unit_of_measurement") if tst else None
                tstats = await recorder.async_add_executor_job(
                    statistics_during_period, self.hass, start, end, {outdoor}, "hour", None, {"mean"}
                )
                for row in tstats.get(outdoor, []):
                    temps[row["start"]] = self._to_celsius(row.get("mean"), tunit)
            fresh = LoadModel()
            boot_days: dict[str, list[float]] = {}
            for row in stats.get(eid, []):
                if row.get("change") is None:
                    continue
                kw = float(row["change"]) * factor
                kw = max(0.0, kw - wb_hour.get(row["start"], 0.0)) if 0.0 <= kw <= MAX_PLAUSIBLE_KW else kw
                t = temps.get(row["start"])
                local = dt_util.as_local(dt_util.utc_from_timestamp(row["start"]))
                if need_model:
                    fresh.add_hourly(local, kw, t)
                if 0.0 <= kw <= MAX_PLAUSIBLE_KW:
                    d = boot_days.setdefault(local.strftime("%Y-%m-%d"), [0.0, 0, 0.0, 0])
                    d[0] += kw * 4
                    d[1] += 4
                    if t is not None:
                        d[2] += t * 4
                        d[3] += 4
            if need_model and self._rebuild:
                # rebuild (0.14.1): the old model may hold charging from the first fill; the quarter hours measured here say
                # how much of each was the wallbox, so they come on top in their order instead of the old samples
                for row in sorted(self.quarters, key=lambda r: r[0]):
                    try:
                        q = dt_util.as_local(dt_util.parse_datetime(row[0]))
                        house = max(0.0, float(row[1]) - float(row[3] or 0.0)) if len(row) > 3 else None
                    except (TypeError, ValueError, IndexError):
                        continue
                    if q is None or house is None or (row[3] is None and self._has_wallbox()):
                        continue
                    dd = self.days.get(q.strftime("%Y-%m-%d")) or boot_days.get(q.strftime("%Y-%m-%d"))
                    fresh.add(q, house, dd[2] / dd[3] if dd and dd[3] else None)
                self.model = fresh
                self._rebuild = False
            elif need_model:
                for slot, values in self.model.slots.items():  # samples measured meanwhile are newer: keep them last
                    fresh.slots.setdefault(slot, []).extend(values)
                    fresh.temps.setdefault(slot, []).extend(self.model.temps.get(slot) or [None] * len(values))
                    del fresh.slots[slot][:-8]
                    del fresh.temps[slot][:-8]
                self.model = fresh
                self._bootstrapped = True
            if outdoor and self.weather_enabled:
                boot_days.update(self.days)  # days measured here are exact: they win
                self.days = boot_days
                self._days_bootstrapped = True
                self._curve_at = None
            self._forecast_at = None  # recompute with the filled model right away
            await self._model_store.async_save(self._model_data())
            _LOGGER.info("Load forecast: %s samples from the statistics, %s days for the weather curve",
                         self.model.samples, len(self.days))
        except Exception as err:  # noqa: BLE001 - the forecast is optional, the guard must not depend on it
            self._bootstrap_failed = True
            _LOGGER.warning("Load forecast: history could not be read: %s", err)
        finally:
            self._bootstrapping = False

    # ---------- house and wallbox apart ----------

    def _has_wallbox(self) -> bool:
        return any(d[D_KIND] in WALLBOX_KINDS for d in self.raw_devices.values())

    def _wb_accumulate(self, now: datetime, readings: dict[str, Reading]) -> None:
        """Energy of all wallboxes in the running quarter hour (for learning the house without the wallbox)."""
        p = wallbox_total_w([(r.power_w, bool(self.raw_devices[dev_id].get(D_OBSERVE))) for dev_id, r in readings.items()
                             if self.raw_devices.get(dev_id, {}).get(D_KIND) in WALLBOX_KINDS]) / 1000.0
        self._wb_kw_now = p
        q = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        w = self._wbq
        if w["q"] != q:
            if w["q"] is not None and w["q"] == q - timedelta(minutes=15):
                self._wb_last = (w["q"], round(w["kwh"] / 0.25, 3))
            w.update({"q": q, "kwh": 0.0, "t": max(q, w["t"]) if w["t"] else now})
        if w["t"] is not None:
            w["kwh"] += p * max(0.0, min(60.0, (now - w["t"]).total_seconds())) / 3600.0
        w["t"] = now

    def _car_may_charge(self) -> bool:
        """False only if a vehicle entry says the car is full or not plugged in (and the wallbox is idle)."""
        if not self._has_wallbox() or self._wb_kw_now >= 1.0:
            return True
        v = self._vehicle()
        if v is None:
            return True
        if v.get(D_CONNECTED) and not self._is_on(v.get(D_CONNECTED), True):
            return False
        soc = self._float(v.get(D_SOC))
        target = self._target(v.get(D_TARGET_ENTITY))
        target = target if target is not None else float(v.get(D_TARGET_SOC, 80))
        return soc is None or soc < target - 0.5

    def _car_unplugged(self) -> bool:
        """True if a vehicle entry says the car is not plugged in (a full car is not 'unplugged': it does not charge today)."""
        v = self._vehicle()
        if v is None or not v.get(D_CONNECTED) or self._is_on(v.get(D_CONNECTED), True):
            return False
        soc = self._float(v.get(D_SOC))
        target = self._target(v.get(D_TARGET_ENTITY))
        target = target if target is not None else float(v.get(D_TARGET_SOC, 80))
        return soc is None or soc < target - 0.5

    def _view_all(self) -> LoadModel:
        return combine(self.model, self.wb_model) if self.wb_model.slots else self.model

    def _view_now(self) -> LoadModel:
        return self._view_all() if self._car_may_charge() else self.model

    # ---------- battery reserve before a forecast peak ----------

    async def _battery_reserve_step(self, now: datetime, execute: bool) -> None:
        """Before a forecast risk window keep the battery charged (one setting, e.g. low output power or a mode),
        afterwards put it back. Only batteries with a reserve setting, only with the switch on. A battery the guard
        has released for an emergency is left alone until it is given back."""
        windows = (self.forecast.get("windows") or []) if self.forecast_enabled else []
        for dev_id, d in self.raw_devices.items():
            if d[D_KIND] != KIND_BATTERY or not d.get(D_RESERVE_ENTITY) or d.get(D_RESERVE_VALUE) in (None, ""):
                continue
            if dev_id in self.guard.interventions:
                continue
            win = reserve_window(windows, now, float(d.get(D_RESERVE_LEAD, 60))) if (
                self.battery_reserve and self.mode != MODE_OFF) else None
            held = self._reserve.get(dev_id)
            name = d.get(D_NAME, dev_id)
            if win is not None and held is None:
                text = self.t("res_hold", name=name, start=f"{win['start']:%H:%M}", end=f"{win['end']:%H:%M}",
                              high=win["high_kw"])
                if not execute:
                    key = win["start"].isoformat()
                    if self._reserve_seen.get(dev_id) != key:
                        self._reserve_seen[dev_id] = key
                        self._log(Action(dev_id, "log", None, text, False), True)
                    continue
                ent, val = d[D_RESERVE_ENTITY], str(d[D_RESERVE_VALUE])
                st = self._state(ent)
                try:
                    await self._set_entity(ent, val)
                except Exception as err:  # noqa: BLE001
                    self._log(Action(dev_id, "log", None, self.t("res_fail", name=name, err=err), False), False)
                    continue
                self._reserve[dev_id] = {"entity": ent, "value": val, "orig": st.state if st else None,
                                         "until": win["end"].isoformat()}
                self._log(Action(dev_id, "log", None, text, False), False)
            elif held is not None and (win is None or not execute):
                await self._end_reserve(dev_id, self.t("r_risk_over") if win is None else self.t("r_mode"))

    async def _end_reserve(self, dev_id: str, reason: str) -> None:
        held = self._reserve.pop(dev_id, None)
        if not held:
            return
        name = self.raw_devices.get(dev_id, {}).get(D_NAME, dev_id)
        st = self._state(held["entity"])
        if held.get("orig") is not None and st is not None and _same_value(st.state, str(held["value"])):
            try:
                await self._set_entity(held["entity"], str(held["orig"]))
            except Exception as err:  # noqa: BLE001
                self._log(Action(dev_id, "log", None, self.t("res_back_fail", name=name, err=err), False), False)
                return
            self._log(Action(dev_id, "log", None, self.t("res_end", reason=reason, name=name), False), False)
        else:
            self._log(Action(dev_id, "log", None, self.t("res_end_changed", reason=reason, name=name), False), False)

    async def _end_reserve_all(self, reason: str) -> None:
        for dev_id in list(self._reserve):
            await self._end_reserve(dev_id, reason)

    # ---------- export ----------

    async def export_csv(self, kind: str = "quarters", days: int = 31, fmt: str = "standard") -> dict[str, Any]:
        """Write the quarter-hour load profile or the daily peaks as CSV to /config/viertelstunden_waechter/export/
        (not a public folder). Returns the path, the number of rows and - for small files - the CSV itself."""
        now = dt_util.now()
        since = now - timedelta(days=max(1, int(days)))
        if kind == "days":
            text, n = days_csv(self.day_peaks, fmt, since.strftime("%Y-%m-%d"))
            name = f"tagesspitzen_{since:%Y-%m-%d}_{now:%Y-%m-%d}.csv"
        else:
            text, n = quarters_csv(self.quarters, fmt, since)
            name = f"lastgang_{since:%Y-%m-%d}_{now:%Y-%m-%d}.csv"
        path = self.hass.config.path(DOMAIN, "export", name)

        def _write() -> None:
            import os

            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)

        await self.hass.async_add_executor_job(_write)
        return {"path": path, "rows": n, "csv": text if n <= 2000 else None}

    # ---------- AI explainer ----------

    async def explain_today(self, push: bool = False) -> dict[str, Any]:
        """A short explanation of today's interventions by the AI task chosen in the settings. Without interventions
        no AI is asked. At most AI_CALLS_PER_DAY calls per day; never switches anything."""
        now = dt_util.now()
        day = now.strftime("%Y-%m-%d")
        lines = self.log_lines(50, today_only=True)
        counts = self.counts.get(day, {})
        interventions = int(counts.get("real", 0)) + int(counts.get("shadow", 0))
        peak = self.day_peaks.get(day, {})
        peak_kw = float(peak["kw"]) if peak.get("kw") is not None else None
        lang = self.hass.config.language
        result: dict[str, Any] = {"date": day, "created": now.isoformat(timespec="seconds"), "source": "rule", "text": ""}
        entity = self.cfg.get(CONF_AI_TASK)
        if interventions == 0:
            result["text"] = plain_summary(lang, 0, peak_kw, self.limit_kw, now.strftime("%d.%m."))
        elif not entity:
            result.update({"source": "none", "error": "no AI task entity in the settings"})
        elif self._ai_calls.get(day, 0) >= AI_CALLS_PER_DAY:
            result.update({"source": "none", "error": f"limit of {AI_CALLS_PER_DAY} AI calls per day reached"})
        else:
            self._ai_calls = {day: self._ai_calls.get(day, 0) + 1}
            instructions = build_instructions(
                lang, now.strftime("%d.%m.%Y"), lines, self.limit_kw,
                float(self.guard.values.get("target_kw") or (self.limit_kw - self.margin_kw)), peak_kw, peak.get("at"),
                interventions, int(counts.get("miss", 0)), self.mode == MODE_OBSERVE,
            )
            try:
                async with asyncio.timeout(90):
                    resp = await self.hass.services.async_call(
                        "ai_task", "generate_data",
                        {"task_name": "Viertelstunden-Wächter", "instructions": instructions, "entity_id": entity},
                        blocking=True, return_response=True,
                    )
                result.update({"source": "ai", "entity": entity, "text": extract_text(resp)})
                if not result["text"]:
                    result.update({"source": "none", "error": "empty answer"})
            except Exception as err:  # noqa: BLE001 - the explainer is optional
                _LOGGER.warning("AI explainer failed: %s", err)
                result.update({"source": "none", "error": str(err)})
        self.explanation = result
        self._store.async_delay_save(self._data, 5)
        if push and result.get("text"):
            await self._exec(Action("", "notify", None, result["text"]))
        async_dispatcher_send(self.hass, self.signal)
        return result

    async def _explain_due(self, now: datetime) -> None:
        """Every evening once, with the switch on."""
        if not self.ai_explainer or now.hour < EXPLAIN_AT_HOUR:
            return
        if self.explanation.get("date") == now.strftime("%Y-%m-%d") and self.explanation.get("auto"):
            return
        await self.explain_today(push=True)
        self.explanation["auto"] = True  # once per evening, also after an error

    # ---------- charge plan ----------

    def _vehicle(self) -> dict[str, Any] | None:
        return next((d for d in self.raw_devices.values() if d[D_KIND] == KIND_VEHICLE), None)

    def _departure(self, entity_id: str | None, now: datetime) -> datetime | None:
        """Next departure from a time (next occurrence) or a date-time entity."""
        st = self._state(entity_id)
        if st is None:
            return None
        parsed = dt_util.parse_datetime(st.state)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            parsed = dt_util.as_local(parsed)
            return parsed if parsed > now else None
        t = dt_util.parse_time(st.state)
        if t is None:
            return None
        cand = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        return cand if cand > now else cand + timedelta(days=1)

    async def _solar_kw(self, now: datetime) -> dict[datetime, float] | None:
        """PV forecast per quarter hour from whatever solar forecast the Energy dashboard uses (Forecast.Solar,
        Solcast, ...). None if there is none: the plan then works without the sun."""
        if self._solar_cache is not None and (now - self._solar_cache[0]) < timedelta(minutes=15):
            return self._solar_cache[1]
        series: dict[datetime, float] | None = None
        try:
            from homeassistant.components.energy.data import async_get_manager
            from homeassistant.components.energy.websocket_api import async_get_energy_platforms

            manager = await async_get_manager(self.hass)
            entries: list[str] = []
            for source in (manager.data or {}).get("energy_sources", []):
                if source.get("type") == "solar":
                    entries += source.get("config_entry_solar_forecast") or []
            if entries:
                platforms = await async_get_energy_platforms(self.hass)
                hourly_kw: dict[datetime, float] = {}
                for entry_id in entries:
                    ce = self.hass.config_entries.async_get_entry(entry_id)
                    if ce is None or ce.domain not in platforms:
                        continue
                    forecast = await platforms[ce.domain](self.hass, entry_id)
                    for iso, wh in ((forecast or {}).get("wh_hours") or {}).items():
                        t = dt_util.parse_datetime(iso)
                        if t is not None:
                            t = dt_util.as_local(t)
                            hourly_kw[t] = hourly_kw.get(t, 0.0) + float(wh) / 1000.0
                if hourly_kw:
                    series = {t.replace(minute=m): kw for t, kw in hourly_kw.items() for m in (0, 15, 30, 45)}
        except Exception as err:  # noqa: BLE001 - the sun is optional
            _LOGGER.debug("Solar forecast not available: %s", err)
            series = None
        self._solar_cache = (now, series)
        return series

    async def _update_plan(self, now: datetime) -> None:
        v = self._vehicle()
        if v is None:
            self.plan = {"status": "no_vehicle"}
            return
        if not self.plan_enabled:
            self.plan = {"status": "off"}
            return
        if self._plan_at is not None and (now - self._plan_at) < timedelta(minutes=5):
            return
        self._plan_at = now
        soc = self._float(v.get(D_SOC))
        departure = self._departure(v.get(D_DEPARTURE), now)
        if soc is None:
            self.plan = {"status": "no_data"}
            return
        if departure is None:
            self.plan = {"status": "no_departure", "soc": soc}
            return
        target = self._target(v.get(D_TARGET_ENTITY))
        target = target if target is not None else float(v.get(D_TARGET_SOC, 80))
        hours = max(2, min(48, int((departure - now).total_seconds() // 3600) + 2))
        series = self.model.horizon(now, hours, **self._wx_args())  # the house without the wallbox: the plan adds the car itself
        solar = await self._solar_kw(now)
        target_kw = float(self.guard.values.get("target_kw") or (self.limit_kw - self.margin_kw))
        plan = make_plan(
            now, departure, soc, target, float(v.get(D_CAPACITY, 60)), float(v.get(D_CHARGE_MAX, 11)),
            float(v.get(D_CHARGE_MIN, 1.4)), target_kw, series, solar, float(v.get(D_BASE, 0.5)),
            float(v.get(D_EFFICIENCY, 90.0)) / 100.0,
        )
        plan["soc"], plan["target_soc"] = soc, target
        self.plan = plan

    def _vehicle_connected(self, v: dict[str, Any]) -> bool:
        return self._is_on(v.get(D_CONNECTED), True) if v.get(D_CONNECTED) else True

    async def _vehicle_command(self, v: dict[str, Any], which: str) -> bool:
        """Run the configured start or stop command. False if none is configured."""
        ent, val = (v.get(D_START), v.get(D_START_VALUE)) if which == "start" else (v.get(D_STOP), v.get(D_STOP_VALUE))
        if not ent:
            return False
        await self._set_entity(ent, str(val if val is not None else ""))
        return True

    async def _execute_plan(self, now: datetime) -> None:
        """Pause the charging outside the planned windows and let it run inside - only with the switch on and only
        while the plan can reach the target. Everything else (switch off, plan infeasible, no departure, restart)
        lets the car charge normally."""
        v = self._vehicle()
        active = (v is not None and self.plan_execute and self.plan_enabled and self.plan.get("status") == "planned"
                  and self._vehicle_connected(v))
        want = charging_allowed(self.plan, now) if active else None
        paused_wanted = want is False
        if v is None or paused_wanted == self._plan_paused:
            return
        if self._plan_cmd_at is not None and active and (now - self._plan_cmd_at) < timedelta(minutes=5):
            return  # at most one command per five minutes while the plan is running; resuming is never delayed
        try:
            if paused_wanted:
                if not v.get(D_STOP):
                    return  # nothing to pause with; the plan stays advice
                await self._vehicle_command(v, "stop")
                self._plan_paused = True
                self._log(Action("", "log", None, self.t("plan_pause"), False), False)
            else:
                if v.get(D_START):
                    await self._vehicle_command(v, "start")
                self._plan_paused = False
                self._log(Action("", "log", None, self.t("plan_go"), False), False)
            self._plan_cmd_at = now
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Charge plan command failed: %s", err)
            self._log(Action("", "log", None, self.t("plan_fail", err=err), False), False)

    # ---------- executing ----------

    async def _run(self, acts: list[Action], execute: bool) -> None:
        for a in acts:
            if a.text:
                self._log(a, not execute)
            if a.kind == "unconfirmed" and execute:
                day = self.counts.setdefault(dt_util.now().strftime("%Y-%m-%d"), {"real": 0, "shadow": 0})
                day["miss"] = day.get("miss", 0) + 1
            if not execute or a.kind == "log":
                continue
            try:
                await self._exec(a)
            except Exception as err:  # noqa: BLE001 - a failing device must not stop the guard
                _LOGGER.warning("Action %s for %s failed: %s", a.kind, a.device_id, err)
                self._log(Action(a.device_id, "log", None, self.t("error", what=a.text or a.kind, err=err), False), False)

    async def _call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        async with asyncio.timeout(CALL_TIMEOUT_S):
            await self.hass.services.async_call(domain, service, data, blocking=True)

    @staticmethod
    def _engine_dict(d: dict[str, Any]) -> dict[str, Any]:
        """What the engine gets of a device: an evcc loadpoint is a wallbox for it (one-phase option is the number of phases)."""
        if d.get(D_KIND) != KIND_EVCC:
            return d
        return {**d, D_KIND: KIND_WALLBOX, "one_phase_option": "1" if d.get(D_EVCC_ONE_PHASE) else None}

    def _evcc_client(self, url: str, password: str) -> EvccClient:
        key = (url, password)
        if key not in self._evcc_clients:
            self._evcc_clients[key] = EvccClient(async_get_clientsession(self.hass), url, password)
        return self._evcc_clients[key]

    async def _poll_evcc(self) -> None:
        """Read evcc once per address and keep the loadpoints of the devices (unreachable = None: the guard leaves the device alone)."""
        states: dict[tuple[str, str], dict[str, Any] | None] = {}

        async def read(key: tuple[str, str]) -> dict[str, Any] | None:
            if key not in states:
                try:
                    states[key] = await self._evcc_client(*key).state()
                    self._evcc_down.discard(key)
                except Exception as err:  # noqa: BLE001 - evcc being down must not stop the guard
                    states[key] = None
                    if key not in self._evcc_down:  # say it once, not every cycle
                        _LOGGER.warning("evcc at %s is not reachable: %s", key[0], err)
                        self._evcc_down.add(key)
            return states[key]

        for dev_id, d in self.raw_devices.items():
            if d.get(D_KIND) != KIND_EVCC:
                continue
            st = await read((str(d.get(D_EVCC_URL) or ""), str(d.get(D_EVCC_PASSWORD) or "")))
            self._evcc_lp[dev_id] = parse_loadpoint(st, int(d.get(D_EVCC_LOADPOINT) or 1)) if st else None
        site_url = str(self.cfg.get(CONF_EVCC_URL) or "")
        self.grid_evcc_kw = parse_grid_kw(await read((site_url, str(self.cfg.get(CONF_EVCC_PASSWORD) or "")))) if site_url else None

    async def _evcc_exec(self, a: Action, d: dict[str, Any]) -> None:
        client = self._evcc_client(str(d.get(D_EVCC_URL) or ""), str(d.get(D_EVCC_PASSWORD) or ""))
        loadpoint = int(d.get(D_EVCC_LOADPOINT) or 1)
        if a.kind == "set_phase":
            await client.set_phases(loadpoint, int(float(a.value)))
            return
        lp = self._evcc_lp.get(a.device_id)
        orig = self._evcc_orig.get(a.device_id)
        if orig is None and a.intervention and lp and lp.get("ceiling") is not None:
            orig = {"ceiling": float(lp["ceiling"]), "virtual": float(virtual_current(lp) or lp["ceiling"])}
            self._evcc_orig[a.device_id] = orig
        amps, restored = target_ceiling(float(a.value), orig)
        await client.set_max_current(loadpoint, amps)
        if restored:
            self._evcc_orig.pop(a.device_id, None)

    async def _exec(self, a: Action) -> None:
        d = self.raw_devices.get(a.device_id, {})
        if d.get(D_KIND) == KIND_EVCC and a.kind in ("set_current", "set_phase"):
            await self._evcc_exec(a, d)
        elif a.kind == "set_current":
            eid = d[D_CURRENT]
            domain = eid.split(".")[0]
            if domain in ("select", "input_select"):   # a list of currents: the entry with the wanted amps (or the next lower one)
                st = self._state(eid)
                options = list(st.attributes.get("options") or []) if st else []
                _cur, steps = self._wallbox_current(eid)
                want = step_down(int(float(a.value)), steps)
                option = next((o for o in options if amps_of(o) == want), None)
                if option is None:
                    raise ValueError(f"no entry with {want} A in {eid}")
                await self._call(domain, "select_option", {"entity_id": eid, "option": option})
            else:
                await self._call(domain, "set_value", {"entity_id": eid, "value": a.value})
        elif a.kind == "set_phase":
            eid = d[D_PHASE]
            await self._call(eid.split(".")[0], "select_option", {"entity_id": eid, "option": a.value})
        elif a.kind in ("turn_off", "turn_on"):
            await self._call("homeassistant", a.kind, {"entity_id": d[D_SWITCH]})
        elif a.kind == "set_value":
            await self._set_entity(d[D_VALUE], str(a.value))
        elif a.kind == "battery_release":
            orig: dict[str, str] = {}
            for ent, val in self._battery_pairs(d):
                st = self._state(ent)
                if st is not None:
                    orig[ent] = st.state
                await self._set_entity(ent, val)
            self._battery_orig[a.device_id] = orig
        elif a.kind == "battery_restore":
            await self._battery_restore(a.device_id, d)
        elif a.kind == "script_on":
            await self._call("script", "turn_on", {"entity_id": d[D_ON_SCRIPT]})
        elif a.kind == "script_off" and d.get(D_OFF_SCRIPT):
            await self._call("script", "turn_on", {"entity_id": d[D_OFF_SCRIPT]})
        elif a.kind in ("notify", "unconfirmed"):
            if a.kind == "unconfirmed":  # a device that keeps ignoring commands must not send a message every cycle
                last = self._miss_push.get(a.device_id)
                if last is not None and (dt_util.now() - last) < timedelta(minutes=30):
                    return
                self._miss_push[a.device_id] = dt_util.now()
            for svc in [s.strip() for s in str(self.cfg.get(CONF_NOTIFY) or "").split(",") if "." in s]:
                domain, service = svc.split(".", 1)
                try:
                    await self._call(domain, service, {"title": self.entry.title, "message": a.text})
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Notification via %s failed: %s", svc, err)

    @staticmethod
    def _battery_pairs(d: dict[str, Any]) -> list[tuple[str, str]]:
        return [(d[e], str(d[v])) for e, v in ((D_REL1, D_REL1_VALUE), (D_REL2, D_REL2_VALUE)) if d.get(e) and d.get(v) not in (None, "")]

    async def _set_entity(self, entity_id: str, value: str) -> None:
        domain = entity_id.split(".")[0]
        if domain in ("number", "input_number"):
            await self._call(domain, "set_value", {"entity_id": entity_id, "value": float(value)})
        elif domain in ("select", "input_select"):
            await self._call(domain, "select_option", {"entity_id": entity_id, "option": value})
        elif domain in ("switch", "input_boolean"):
            await self._call("homeassistant", "turn_on" if value == "on" else "turn_off", {"entity_id": entity_id})
        elif domain == "button":
            await self._call("button", "press", {"entity_id": entity_id})
        else:
            raise ValueError(f"unsupported entity {entity_id}")

    async def _battery_restore(self, dev_id: str, d: dict[str, Any]) -> None:
        """Put the settings back that the release changed - but only those that still hold the release value."""
        orig = self._battery_orig.pop(dev_id, {})
        if d.get(D_RESTORE_ORIG, True):
            for ent, val in self._battery_pairs(d):
                before = orig.get(ent)
                st = self._state(ent)
                if before is not None and st is not None and _same_value(st.state, val):
                    await self._set_entity(ent, before)
        if d.get(D_OFF_SCRIPT):
            await self._call("script", "turn_on", {"entity_id": d[D_OFF_SCRIPT]})

    def _log(self, a: Action, shadow: bool) -> None:
        now = dt_util.now()
        self.log = ([{"t": now.isoformat(timespec="seconds"), "text": a.text, "shadow": shadow}] + self.log)[:LOG_KEEP]
        if a.intervention and a.kind not in ("log",):
            day = self.counts.setdefault(now.strftime("%Y-%m-%d"), {"real": 0, "shadow": 0})
            day["shadow" if shadow else "real"] += 1
            for k in sorted(self.counts)[:-40]:
                del self.counts[k]
        _LOGGER.info("%s%s", "[observe] " if shadow else "", a.text)

    def _data(self) -> dict[str, Any]:
        return {
            "log": self.log,
            "counts": self.counts,
            "month_peak": self.month_peak,
            "months": self.months,
            "battery_orig": self._battery_orig,
            "evcc_orig": self._evcc_orig,
            "plan_paused": self._plan_paused,
            "day_peaks": self.day_peaks,
            "weekly": self.weekly,
            "explanation": self.explanation,
            "ai_calls": self._ai_calls,
            "usage": self._usage,
            "reserve": self._reserve,
            "last_quarter_kw": self.last_quarter_kw,
            "executing": self.executing,
            "interventions": self.guard.interventions if self.executing else {},
            "quarter": self.guard.quarter_state(),
        }

    # ---------- for the entities ----------

    def log_lines(self, limit: int = 10, today_only: bool = False) -> list[str]:
        today = dt_util.now().strftime("%Y-%m-%d")
        lines = []
        for x in self.log:
            if today_only and not x["t"].startswith(today):
                continue
            t = dt_util.parse_datetime(x["t"])
            stamp = t.strftime("%H:%M:%S" if today_only else "%d.%m. %H:%M:%S") if t else x["t"]
            lines.append(f"{stamp}  {self.t('observed') + ' ' if x.get('shadow') else ''}{x['text']}")
            if len(lines) >= limit:
                break
        return lines

    def configuration(self) -> dict[str, Any]:
        """What is configured, for the status attribute, the dashboard and diagnostics."""
        devices = sorted(self.raw_devices.values(), key=lambda d: int(d.get("priority", 5)))
        return {
            "grid_power": self.cfg.get(CONF_GRID_POWER),
            "evcc_grid": bool(self.cfg.get(CONF_EVCC_URL)),
            "grid_energy": self.cfg.get(CONF_GRID_ENERGY),
            "condition": self.cfg.get(CONF_CONDITION),
            "lock": self.cfg.get(CONF_LOCK),
            "notify": self.cfg.get(CONF_NOTIFY),
            "devices": [{k: v for k, v in d.items() if k != D_ID} for d in devices],
        }

    def import_history(self, days: list[dict[str, Any]], months: list[dict[str, Any]]) -> dict[str, int]:
        """Seed the peaks from an earlier measurement (e.g. a spreadsheet or an older script). Only raises values:
        a day or month that already has a higher peak keeps it. Values from hourly data are lower bounds."""
        n_days = n_months = 0
        for d in days:
            date, kw = str(d.get("date", ""))[:10], float(d.get("kw", 0.0))
            if len(date) == 10 and kw > 0 and kw > float(self.day_peaks.get(date, {}).get("kw") or 0.0):
                self.day_peaks[date] = {"kw": round(kw, 3), "at": str(d.get("at") or "")}
                n_days += 1
        for k in sorted(self.day_peaks)[:-DAYS_KEEP]:
            del self.day_peaks[k]
        for m in months:
            month, kw = str(m.get("month", ""))[:7], float(m.get("peak_kw", 0.0))
            if len(month) == 7 and kw > 0:
                cur = self.months.setdefault(month, {"kw": 0.0, "ug": 0.0})
                if kw > float(cur.get("kw") or 0.0):
                    cur["kw"] = round(kw, 3)
                    n_months += 1
                cur["ug"] = max(float(cur.get("ug") or 0.0), float(cur["kw"]))
                if self.month_peak.get("month") == month and kw > float(self.month_peak.get("kw") or 0.0):
                    self.month_peak = {"month": month, "kw": round(kw, 3), "at": None}
        for k in sorted(self.months)[:-15]:
            del self.months[k]
        self._store.async_delay_save(self._data, 1)
        return {"days": n_days, "months": n_months}

    def today_quarters(self) -> list[list[Any]]:
        """Finished quarter hours of today as [HH:MM, kW] (for the phone view)."""
        today = dt_util.now().strftime("%Y-%m-%d")
        return [[str(r[0])[11:16], r[1]] for r in self.quarters if str(r[0]).startswith(today) and r[1] is not None]

    def recent_lines(self, limit: int = 6) -> list[str]:
        return self.log_lines(limit)

    def intervention_names(self) -> list[str]:
        return [self.raw_devices[i].get("name", i) for i in self.guard.interventions if i in self.raw_devices]
