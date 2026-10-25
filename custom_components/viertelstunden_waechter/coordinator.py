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
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONDITION, CONF_GRID_ENERGY, CONF_GRID_POWER, CONF_LIMIT, CONF_LOCK, CONF_MARGIN,
    CONF_NOTIFY, D_ALLOW, D_CURRENT, D_ID, D_KIND, D_NAME, D_OFF_SCRIPT, D_ON_SCRIPT, D_PHASE, D_PHASES, D_POWER,
    D_RESTORE, D_SWITCH, DOMAIN, MODE_ACTIVE, MODE_OBSERVE, MODE_OFF, UPDATE_INTERVAL,
    D_BASE, D_CAPACITY, D_CHARGE_MAX, D_CHARGE_MIN, D_CONNECTED, D_DEPARTURE, D_START, D_START_VALUE, D_STOP,
    D_STOP_VALUE, D_TARGET_ENTITY, D_TARGET_SOC,
    D_COMFORT, D_MIN_SOC, D_REL1, D_REL1_VALUE, D_REL2, D_REL2_VALUE, D_RESTORE_ORIG, D_SOC, D_VALUE,
)
from .forecast import LoadModel, hourly, risk_windows, weekly_profile
from .plan import charging_allowed, make_plan
from .pricing import monthly_cost
from .engine import (
    KIND_BATTERY, KIND_SCRIPT, KIND_SETTING, KIND_VEHICLE, KIND_SWITCH, KIND_THROTTLE, KIND_WALLBOX, STRATEGY_COMFORT, Action,
    DeviceConfig, Guard, Reading,
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
DAYS_KEEP = 62
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
        self.guard = Guard(
            [DeviceConfig.from_dict(d) for d in self.raw_devices.values() if d[D_KIND] != KIND_VEHICLE], STRATEGY_COMFORT
        )
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
        self.model = LoadModel()
        self.forecast: dict[str, Any] = {}
        self._forecast_at: datetime | None = None
        self._bootstrapped = False
        self._bootstrapping = False
        self._bootstrap_failed = False
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
        self._battery_orig = data.get("battery_orig", {})
        self._plan_paused = bool(data.get("plan_paused"))  # resumed by the first cycle (the plan switch is off)
        if self.month_peak.get("month") and self.month_peak["month"] not in self.months:
            kw = float(self.month_peak.get("kw") or 0.0)  # taken over from version 0.2
            self.months[self.month_peak["month"]] = {"kw": kw, "ug": kw}
        self.last_quarter_kw = data.get("last_quarter_kw")
        model_data = await self._model_store.async_load() or {}
        self.model = LoadModel.from_dict(model_data)
        self._bootstrapped = bool(model_data.get("bootstrapped"))
        if data.get("executing") and data.get("interventions"):
            # Home Assistant restarted while the guard had changed devices: give them back first
            self.guard.load({"interventions": data["interventions"]})
            await self._run(self.guard.release_all(dt_util.now(), self._readings(), "Neustart"), True)
        self.guard.forget()
        self._unsub = async_track_time_interval(self.hass, self._tick, UPDATE_INTERVAL)

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        async with self._lock:
            self.plan_execute = False
            await self._execute_plan(dt_util.now())  # resume a charging the plan had paused
            if self.executing and self.guard.interventions:
                await self._run(self.guard.release_all(dt_util.now(), self._readings(), "Integration beendet"), True)
            self.executing = False
            self.guard.forget()
        await self._store.async_save(self._data())

    async def async_set_mode(self, mode: str) -> None:
        self.mode = mode
        if self._unsub is not None:
            await self._tick()

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

    def _power_kw(self, eid: str | None) -> float | None:
        v = self._float(eid)
        if v is None:
            return None
        unit = (self.hass.states.get(eid).attributes.get("unit_of_measurement") or "W").strip()
        return v * {"W": 0.001, "kW": 1.0, "MW": 1000.0}.get(unit, 0.001)

    def _energy_kwh(self, eid: str | None) -> float | None:
        v = self._float(eid)
        if v is None:
            return None
        unit = (self.hass.states.get(eid).attributes.get("unit_of_measurement") or "kWh").strip()
        return v * {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}.get(unit, 1.0)

    def _is_on(self, eid: str | None, unknown: bool) -> bool:
        if not eid:
            return unknown
        st = self._state(eid)
        return unknown if st is None else st.state == "on"

    def _readings(self) -> dict[str, Reading]:
        out: dict[str, Reading] = {}
        for dev_id, d in self.raw_devices.items():
            if d[D_KIND] == KIND_VEHICLE:
                continue
            r = Reading(allowed=self._is_on(d.get(D_ALLOW), False) if d.get(D_ALLOW) else True)
            p = self._power_kw(d.get(D_POWER))
            r.power_w = p * 1000.0 if p is not None else None
            kind = d[D_KIND]
            if kind == KIND_WALLBOX:
                r.current_a = self._float(d.get(D_CURRENT))
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
            readings = self._readings()
            locked = self._is_on(self.cfg.get(CONF_LOCK), False)
            execute = self.mode == MODE_ACTIVE and not locked
            if execute != self.executing:
                if self.executing:  # leaving active mode: give back what was really changed
                    await self._run(self.guard.release_all(now, readings, "Betriebsart geändert"), True)
                self.guard.forget()  # interventions seen in observe mode never happened
                self.executing = execute
            needed = self._is_on(self.cfg.get(CONF_CONDITION), True)
            grid = self._power_kw(self.cfg.get(CONF_GRID_POWER))
            self.guard.real_effect = execute
            acts = self.guard.step(
                now,
                max(0.0, grid) if grid is not None else None,
                self._energy_kwh(self.cfg.get(CONF_GRID_ENERGY)),
                readings,
                self.effective_limit(now),
                self.margin_kw,
                self.mode != MODE_OFF and needed,
            )
            await self._run(acts, execute)
            if execute:
                await self._push_intervention(acts, now)
            if self.guard.finished_quarter_kw is not None:
                self._quarter_done(self.guard.finished_quarter_kw, self.guard.finished_unguarded_kw, now)
            self._maybe_bootstrap()
            self._update_forecast(now)
            await self._update_plan(now)
            await self._execute_plan(now)
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
        """Message at the first real intervention (not for releases), at most every 30 minutes."""
        if not self.notify_intervention:
            return
        first = next((a for a in acts if a.intervention and a.text and a.kind in
                      ("set_current", "set_phase", "turn_off", "script_on")), None)
        if first is None or (self._last_push is not None and (now - self._last_push) < timedelta(minutes=30)):
            return
        self._last_push = now
        await self._exec(Action("", "notify", None, f"Eingriff: {first.text}"))

    def _quarter_done(self, kw: float, unguarded_kw: float | None, now: datetime) -> None:
        self.last_quarter_kw = kw
        start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0) - timedelta(minutes=15)
        month = start.strftime("%Y-%m")
        m = self.months.setdefault(month, {"kw": 0.0, "ug": 0.0})
        m["kw"] = max(float(m.get("kw") or 0.0), kw)
        m["ug"] = max(float(m.get("ug") or 0.0), kw, unguarded_kw or 0.0)
        for k in sorted(self.months)[:-15]:
            del self.months[k]
        if self.forecast_enabled:  # learn what the load would be without the guard
            self.model.add(start, unguarded_kw if unguarded_kw is not None else kw)
            self._model_store.async_delay_save(self._model_data, 120)
        if self.month_peak.get("month") != month or kw > float(self.month_peak.get("kw") or 0.0):
            self.month_peak = {"month": month, "kw": kw, "at": start.isoformat()}
        day = start.strftime("%Y-%m-%d")
        if kw > float(self.day_peaks.get(day, {}).get("kw") or 0.0):
            self.day_peaks[day] = {"kw": kw, "at": start.strftime("%H:%M")}
        for k in sorted(self.day_peaks)[:-DAYS_KEEP]:
            del self.day_peaks[k]

    # ---------- load forecast ----------

    def _model_data(self) -> dict[str, Any]:
        return {**self.model.to_dict(), "bootstrapped": self._bootstrapped}

    def _update_forecast(self, now: datetime) -> None:
        if not self.forecast_enabled:
            self.forecast = {}
            return
        if self._forecast_at is not None and (now - self._forecast_at) < timedelta(minutes=5):
            return
        self._forecast_at = now
        target = float(self.guard.values.get("target_kw") or (self.limit_kw - self.margin_kw))
        series = self.model.horizon(now, 24)
        highs = [q["high"] for q in series if q["high"] is not None]
        self.forecast = {
            "target": target,
            "now": series[0],
            "peak": max(highs) if highs else None,
            "windows": risk_windows(series, target),
            "hours": hourly(series),
            "profile": weekly_profile(self.model),
            "samples": self.model.samples,
            "slots": self.model.slots_with_data,
        }

    def _maybe_bootstrap(self) -> None:
        """Once: fill the model from the hourly statistics of the grid import counter (lower bounds)."""
        if (not self.forecast_enabled or self._bootstrapped or self._bootstrapping or self._bootstrap_failed
                or not self.cfg.get(CONF_GRID_ENERGY)):
            return
        self._bootstrapping = True
        self.entry.async_create_background_task(self.hass, self._bootstrap(), f"{DOMAIN} history")

    async def _bootstrap(self) -> None:
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            eid = self.cfg[CONF_GRID_ENERGY]
            st = self.hass.states.get(eid)
            unit = ((st.attributes.get("unit_of_measurement") if st else None) or "kWh").strip()
            factor = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}.get(unit, 1.0)
            end = dt_util.now()
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period, self.hass, end - timedelta(days=84), end, {eid}, "hour", None, {"change"}
            )
            fresh = LoadModel()
            for row in stats.get(eid, []):
                if row.get("change") is None:
                    continue
                fresh.add_hourly(dt_util.as_local(dt_util.utc_from_timestamp(row["start"])), float(row["change"]) * factor)
            for slot, values in self.model.slots.items():  # samples measured meanwhile are newer: keep them last
                fresh.slots.setdefault(slot, []).extend(values)
                del fresh.slots[slot][:-8]
            self.model = fresh
            self._bootstrapped = True
            self._forecast_at = None  # recompute with the filled model right away
            await self._model_store.async_save(self._model_data())
            _LOGGER.info("Load forecast: %s samples from the statistics", self.model.samples)
        except Exception as err:  # noqa: BLE001 - the forecast is optional, the guard must not depend on it
            self._bootstrap_failed = True
            _LOGGER.warning("Load forecast: history could not be read: %s", err)
        finally:
            self._bootstrapping = False

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
        target = self._float(v.get(D_TARGET_ENTITY))
        target = target if target is not None else float(v.get(D_TARGET_SOC, 80))
        hours = max(2, min(48, int((departure - now).total_seconds() // 3600) + 2))
        series = self.model.horizon(now, hours)
        solar = await self._solar_kw(now)
        target_kw = float(self.guard.values.get("target_kw") or (self.limit_kw - self.margin_kw))
        plan = make_plan(
            now, departure, soc, target, float(v.get(D_CAPACITY, 60)), float(v.get(D_CHARGE_MAX, 11)),
            float(v.get(D_CHARGE_MIN, 1.4)), target_kw, series, solar, float(v.get(D_BASE, 0.5)),
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
                self._log(Action("", "log", None, "Ladeplan: Laden pausiert (außerhalb der geplanten Zeiten)", False), False)
            else:
                if v.get(D_START):
                    await self._vehicle_command(v, "start")
                self._plan_paused = False
                self._log(Action("", "log", None, "Ladeplan: Laden freigegeben", False), False)
            self._plan_cmd_at = now
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Charge plan command failed: %s", err)
            self._log(Action("", "log", None, f"Ladeplan: Befehl fehlgeschlagen ({err})", False), False)

    # ---------- executing ----------

    async def _run(self, acts: list[Action], execute: bool) -> None:
        for a in acts:
            if a.text:
                self._log(a, not execute)
            if not execute or a.kind == "log":
                continue
            try:
                await self._exec(a)
            except Exception as err:  # noqa: BLE001 - a failing device must not stop the guard
                _LOGGER.warning("Action %s for %s failed: %s", a.kind, a.device_id, err)
                self._log(Action(a.device_id, "log", None, f"Fehler: {a.text or a.kind} ({err})", False), False)

    async def _call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        async with asyncio.timeout(CALL_TIMEOUT_S):
            await self.hass.services.async_call(domain, service, data, blocking=True)

    async def _exec(self, a: Action) -> None:
        d = self.raw_devices.get(a.device_id, {})
        if a.kind == "set_current":
            eid = d[D_CURRENT]
            await self._call(eid.split(".")[0], "set_value", {"entity_id": eid, "value": a.value})
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
        elif a.kind == "notify":
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
            "plan_paused": self._plan_paused,
            "day_peaks": self.day_peaks,
            "last_quarter_kw": self.last_quarter_kw,
            "executing": self.executing,
            "interventions": self.guard.interventions if self.executing else {},
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
            lines.append(f"{stamp}  {'(beobachtet) ' if x.get('shadow') else ''}{x['text']}")
            if len(lines) >= limit:
                break
        return lines

    def configuration(self) -> dict[str, Any]:
        """What is configured, for the status attribute, the dashboard and diagnostics."""
        devices = sorted(self.raw_devices.values(), key=lambda d: int(d.get("priority", 5)))
        return {
            "grid_power": self.cfg.get(CONF_GRID_POWER),
            "grid_energy": self.cfg.get(CONF_GRID_ENERGY),
            "condition": self.cfg.get(CONF_CONDITION),
            "lock": self.cfg.get(CONF_LOCK),
            "notify": self.cfg.get(CONF_NOTIFY),
            "devices": [{k: v for k, v in d.items() if k != D_ID} for d in devices],
        }

    def intervention_names(self) -> list[str]:
        return [self.raw_devices[i].get("name", i) for i in self.guard.interventions if i in self.raw_devices]
