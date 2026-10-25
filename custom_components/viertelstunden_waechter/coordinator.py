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
)
from .engine import (
    KIND_SCRIPT, KIND_SWITCH, KIND_WALLBOX, STRATEGY_COMFORT, Action, DeviceConfig, Guard, Reading,
)

_LOGGER = logging.getLogger(__name__)
_BAD = (None, "", STATE_UNKNOWN, STATE_UNAVAILABLE)
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
        self.guard = Guard([DeviceConfig.from_dict(d) for d in self.raw_devices.values()], STRATEGY_COMFORT)
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
        self.last_quarter_kw = data.get("last_quarter_kw")
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
            acts = self.guard.step(
                now,
                max(0.0, grid) if grid is not None else None,
                self._energy_kwh(self.cfg.get(CONF_GRID_ENERGY)),
                readings,
                self.limit_kw,
                self.margin_kw,
                self.mode != MODE_OFF and needed,
            )
            await self._run(acts, execute)
            if self.guard.finished_quarter_kw is not None:
                self._quarter_done(self.guard.finished_quarter_kw, now)
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

    def _quarter_done(self, kw: float, now: datetime) -> None:
        self.last_quarter_kw = kw
        start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0) - timedelta(minutes=15)
        month = start.strftime("%Y-%m")
        if self.month_peak.get("month") != month or kw > float(self.month_peak.get("kw") or 0.0):
            self.month_peak = {"month": month, "kw": kw, "at": start.isoformat()}
        day = start.strftime("%Y-%m-%d")
        if kw > float(self.day_peaks.get(day, {}).get("kw") or 0.0):
            self.day_peaks[day] = {"kw": kw, "at": start.strftime("%H:%M")}
        for k in sorted(self.day_peaks)[:-DAYS_KEEP]:
            del self.day_peaks[k]

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
