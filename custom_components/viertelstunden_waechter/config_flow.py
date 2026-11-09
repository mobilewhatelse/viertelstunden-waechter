"""Set-up dialog, general settings (options) and the devices as config subentries.

Devices are subentries: Home Assistant lists them on the integration page with "Add", "Reconfigure" and
"Delete" - no custom menu needed.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentryFlow, OptionsFlow, SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector, ConfigEntrySelector, ConfigEntrySelectorConfig, EntitySelector, EntitySelectorConfig, NumberSelector, NumberSelectorConfig, NumberSelectorMode,
    SelectSelector, SelectSelectorConfig, TextSelector, TextSelectorConfig, TextSelectorType,
)

from .const import (
    CONF_CONDITION, CONF_GRID_ENERGY, CONF_GRID_POWER, CONF_LIMIT, CONF_LOCK, CONF_MARGIN, CONF_NOTIFY,
    CONF_STARTUP_MODE, CONF_VOLTAGE, CONF_AI_TASK, CONF_CHARGE_PLAN, CONF_MAX_AGE, CONF_OUTDOOR_TEMP, CONF_PLANNER, CONF_WEATHER, DEFAULT_MAX_AGE_S, D_RESERVE_ENTITY, D_RESERVE_LEAD, D_RESERVE_VALUE, D_ALLOW, D_CURRENT, D_KIND, D_MAX_CURRENT, D_MAX_OFF, D_MIN_CURRENT, D_MIN_POWER, D_NAME,
    D_OFF_SCRIPT, D_ON_SCRIPT, D_ONE_PHASE, D_PHASE, D_PHASES, D_POWER, D_POWER_W, D_PRIORITY, D_RESTORE,
    D_SWITCH, DOMAIN, STARTUP_MODES, STARTUP_RESTORE,
    D_BASE, D_EFFICIENCY, D_CAPACITY, D_CHARGE_MAX, D_CHARGE_MIN, D_CONNECTED, D_DEPARTURE, D_START, D_START_VALUE, D_STOP,
    D_STOP_VALUE, D_TARGET_ENTITY, D_TARGET_SOC,
    D_COMFORT, D_COMFORT_MIN, D_HOLD, D_OBSERVE, D_MAX_VALUE, D_MIN_SOC, D_MIN_VALUE, D_PAUSE, D_REL1, D_REL1_VALUE, D_REL2,
    D_REL2_VALUE, D_RESTORE_ORIG, D_SOC, D_STEP, D_VALUE,
)
from .engine import KIND_BATTERY, KIND_EVCC, KIND_SCRIPT, KIND_SETTING, KIND_SWITCH, KIND_THROTTLE, KIND_VEHICLE, KIND_WALLBOX
from .const import CONF_EVCC_BACKUP, CONF_EVCC_PASSWORD, CONF_EVCC_URL, D_EVCC_LOADPOINT, D_EVCC_ONE_PHASE, D_EVCC_PASSWORD, D_EVCC_URL
from .evcc import EvccAuthError, EvccClient, EvccError, parse_grid_kw, parse_loadpoint
from .inputs import unit_errors

ON_OFF_DOMAINS = ["binary_sensor", "input_boolean", "switch"]
RELEASE_DOMAINS = ["number", "input_number", "select", "input_select", "switch", "input_boolean"]
COMMAND_DOMAINS = RELEASE_DOMAINS + ["button"]
TIME_DOMAINS = ["time", "datetime", "input_datetime", "sensor"]


def _num(lo: float, hi: float, step: float = 1, unit: str | None = None) -> NumberSelector:
    if unit is None:  # the selector rejects unit_of_measurement=None
        return NumberSelector(NumberSelectorConfig(min=lo, max=hi, step=step, mode=NumberSelectorMode.BOX))
    return NumberSelector(NumberSelectorConfig(min=lo, max=hi, step=step, mode=NumberSelectorMode.BOX, unit_of_measurement=unit))


def _ent(domain: str | list[str], device_class: str | None = None) -> EntitySelector:
    if device_class:
        return EntitySelector(EntitySelectorConfig(domain=domain, device_class=device_class))
    return EntitySelector(EntitySelectorConfig(domain=domain))


def _opt(key: str, d: dict[str, Any]) -> vol.Optional:
    return vol.Optional(key, description={"suggested_value": d.get(key)})


def _general_schema(d: dict[str, Any], first: bool) -> vol.Schema:
    s: dict[Any, Any] = {}
    if first:
        s[vol.Required("name", default="Viertelstunden-Wächter")] = TextSelector()
    # any sensor: a template sensor with the unit W but without a device class is just as good (the unit is checked on saving)
    s[_opt(CONF_GRID_POWER, d)] = _ent("sensor")
    s[_opt(CONF_EVCC_URL, d)] = TextSelector()
    s[_opt(CONF_EVCC_PASSWORD, d)] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
    if not first:
        s[vol.Required(CONF_EVCC_BACKUP, default=bool(d.get(CONF_EVCC_BACKUP, True)))] = BooleanSelector()
    s[_opt(CONF_GRID_ENERGY, d)] = _ent("sensor")
    if first:
        s[vol.Required(CONF_LIMIT, default=10.0)] = _num(1, 50, 0.1, "kW")
        s[vol.Required(CONF_MARGIN, default=0.5)] = _num(0, 5, 0.1, "kW")
    else:
        s[_opt(CONF_CONDITION, d)] = _ent(ON_OFF_DOMAINS)
        s[_opt(CONF_LOCK, d)] = _ent(ON_OFF_DOMAINS)
        s[_opt(CONF_NOTIFY, d)] = TextSelector()
        s[vol.Required(CONF_VOLTAGE, default=d.get(CONF_VOLTAGE, 230))] = _num(100, 260, 1, "V")
        s[vol.Required(CONF_MAX_AGE, default=d.get(CONF_MAX_AGE, DEFAULT_MAX_AGE_S))] = _num(0, 3600, 10, "s")
        s[_opt(CONF_AI_TASK, d)] = _ent("ai_task")
        s[_opt(CONF_WEATHER, d)] = _ent("weather")
        s[_opt(CONF_OUTDOOR_TEMP, d)] = _ent("sensor", "temperature")
        s[_opt(CONF_PLANNER, d)] = ConfigEntrySelector(ConfigEntrySelectorConfig(integration="plugwhen"))
        s[_opt(CONF_CHARGE_PLAN, d)] = EntitySelector(EntitySelectorConfig(domain="sensor", multiple=True))
        s[vol.Required(CONF_STARTUP_MODE, default=d.get(CONF_STARTUP_MODE, STARTUP_RESTORE))] = SelectSelector(
            SelectSelectorConfig(options=STARTUP_MODES, translation_key=CONF_STARTUP_MODE)
        )
    return vol.Schema(s)


LOCAL_EVCC_URLS = ("http://localhost:7070",)   # evcc on the same machine as Home Assistant (add-on, or Docker with host network)
PROBE_TIMEOUT_S = 2.0


async def find_local_evcc(hass: Any, need_grid: bool = False) -> str | None:
    """The address of an evcc on the same machine, if one answers there within two seconds. Offered in the dialogs, never
    forced: nothing is saved unless the form is saved with it. `need_grid`: only an evcc that reports a grid meter (the
    general settings use evcc for the grid import and would refuse one without). An evcc that wants a password counts."""
    for url in LOCAL_EVCC_URLS:
        try:
            state = await EvccClient(async_get_clientsession(hass), url, None, timeout=PROBE_TIMEOUT_S).state()
        except EvccAuthError:
            return url
        except EvccError:
            continue
        if not need_grid or parse_grid_kw(state) is not None:
            return url
    return None


async def _grid_source_errors(hass: Any, u: dict[str, Any]) -> dict[str, str]:
    """At least one source of the grid import is needed; an evcc address is tried right away (and must have a grid meter)."""
    url = str(u.get(CONF_EVCC_URL) or "").strip()
    if not u.get(CONF_GRID_POWER) and not url:
        return {CONF_GRID_POWER: "grid_source_missing"}
    if not url:
        return {}
    try:
        state = await EvccClient(async_get_clientsession(hass), url, u.get(CONF_EVCC_PASSWORD)).state()
    except EvccAuthError:
        return {CONF_EVCC_PASSWORD: "evcc_auth"}
    except EvccError:
        return {CONF_EVCC_URL: "evcc_unreachable"}
    if parse_grid_kw(state) is None:
        return {CONF_EVCC_URL: "evcc_no_grid"}
    return {}


def _device_schema(kind: str, d: dict[str, Any]) -> vol.Schema:
    s: dict[Any, Any] = {vol.Required(D_NAME, default=d.get(D_NAME, vol.UNDEFINED)): TextSelector()}
    if kind != KIND_VEHICLE:
        s[vol.Required(D_PRIORITY, default=d.get(D_PRIORITY, 1 if kind in (KIND_WALLBOX, KIND_EVCC) else 5 if kind == KIND_SWITCH else 10))] = _num(1, 10)
    if kind == KIND_VEHICLE:
        s[vol.Required(D_SOC, default=d.get(D_SOC, vol.UNDEFINED))] = _ent("sensor")
        s[vol.Required(D_TARGET_SOC, default=d.get(D_TARGET_SOC, 80))] = _num(1, 100, 1, "%")
        s[_opt(D_TARGET_ENTITY, d)] = _ent(["sensor", "number", "input_number"])
        s[vol.Required(D_CAPACITY, default=d.get(D_CAPACITY, 60))] = _num(5, 300, 0.5, "kWh")
        s[vol.Required(D_DEPARTURE, default=d.get(D_DEPARTURE, vol.UNDEFINED))] = _ent(TIME_DOMAINS)
        s[_opt(D_CONNECTED, d)] = _ent(ON_OFF_DOMAINS)
        s[vol.Required(D_CHARGE_MAX, default=d.get(D_CHARGE_MAX, 11))] = _num(1.4, 50, 0.1, "kW")
        s[vol.Required(D_CHARGE_MIN, default=d.get(D_CHARGE_MIN, 1.4))] = _num(0.5, 20, 0.1, "kW")
        s[vol.Required(D_BASE, default=d.get(D_BASE, 0.5))] = _num(0, 20, 0.1, "kW")
        s[vol.Required(D_EFFICIENCY, default=d.get(D_EFFICIENCY, 90))] = _num(50, 100, 1, "%")
        s[_opt(D_START, d)] = _ent(COMMAND_DOMAINS)
        s[_opt(D_START_VALUE, d)] = TextSelector()
        s[_opt(D_STOP, d)] = _ent(COMMAND_DOMAINS)
        s[_opt(D_STOP_VALUE, d)] = TextSelector()
    elif kind == KIND_EVCC:
        s[vol.Required(D_EVCC_URL, default=d.get(D_EVCC_URL, vol.UNDEFINED))] = TextSelector()
        s[vol.Required(D_EVCC_LOADPOINT, default=d.get(D_EVCC_LOADPOINT, 1))] = _num(1, 20)
        s[_opt(D_EVCC_PASSWORD, d)] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
        s[vol.Required(D_MIN_CURRENT, default=d.get(D_MIN_CURRENT, 6))] = _num(6, 32, 1, "A")
        s[vol.Required(D_MAX_CURRENT, default=d.get(D_MAX_CURRENT, 16))] = _num(6, 32, 1, "A")
        s[vol.Required(D_EVCC_ONE_PHASE, default=bool(d.get(D_EVCC_ONE_PHASE, False)))] = BooleanSelector()
        s[_opt(D_POWER, d)] = _ent("sensor")
        s[_opt(D_ALLOW, d)] = _ent(ON_OFF_DOMAINS)
    elif kind == KIND_WALLBOX:
        s[vol.Required(D_POWER, default=d.get(D_POWER, vol.UNDEFINED))] = _ent("sensor")
        s[vol.Required(D_CURRENT, default=d.get(D_CURRENT, vol.UNDEFINED))] = _ent(["number", "input_number"])
        s[vol.Required(D_MIN_CURRENT, default=d.get(D_MIN_CURRENT, 6))] = _num(1, 32, 1, "A")
        s[vol.Required(D_MAX_CURRENT, default=d.get(D_MAX_CURRENT, 16))] = _num(1, 63, 1, "A")
        s[_opt(D_PHASE, d)] = _ent(["select", "input_select"])
        s[_opt(D_ONE_PHASE, d)] = TextSelector()
        s[_opt(D_PHASES, d)] = _ent("sensor")
    elif kind == KIND_SWITCH:
        s[vol.Required(D_SWITCH, default=d.get(D_SWITCH, vol.UNDEFINED))] = _ent(["switch", "input_boolean", "light", "fan"])
        s[_opt(D_POWER, d)] = _ent("sensor")
        s[vol.Required(D_MIN_POWER, default=d.get(D_MIN_POWER, 100))] = _num(0, 20000, 10, "W")
        s[vol.Required(D_POWER_W, default=d.get(D_POWER_W, 0))] = _num(0, 20000, 10, "W")
        s[vol.Required(D_MAX_OFF, default=d.get(D_MAX_OFF, 0))] = _num(0, 1440, 1, "min")
        s[vol.Required(D_PAUSE, default=d.get(D_PAUSE, 0))] = _num(0, 240, 1, "min")
        s[_opt(D_RESTORE, d)] = _ent(ON_OFF_DOMAINS)
    elif kind == KIND_SETTING:
        s[vol.Required(D_REL1, default=d.get(D_REL1, vol.UNDEFINED))] = _ent(RELEASE_DOMAINS)
        s[vol.Required(D_REL1_VALUE, default=d.get(D_REL1_VALUE, vol.UNDEFINED))] = TextSelector()
        s[_opt(D_REL2, d)] = _ent(RELEASE_DOMAINS)
        s[_opt(D_REL2_VALUE, d)] = TextSelector()
        s[vol.Required(D_POWER_W, default=d.get(D_POWER_W, 1500))] = _num(10, 50000, 10, "W")
        s[_opt(D_COMFORT, d)] = _ent("sensor")
        s[vol.Required(D_COMFORT_MIN, default=d.get(D_COMFORT_MIN, 20))] = _num(-50, 1000, 0.5)
        s[vol.Required(D_HOLD, default=d.get(D_HOLD, 0))] = _num(0, 240, 1, "min")
        s[vol.Required(D_PAUSE, default=d.get(D_PAUSE, 0))] = _num(0, 240, 1, "min")
        s[vol.Required(D_MAX_OFF, default=d.get(D_MAX_OFF, 0))] = _num(0, 1440, 1, "min")
        s[vol.Required(D_RESTORE_ORIG, default=d.get(D_RESTORE_ORIG, True))] = BooleanSelector()
        s[_opt(D_OFF_SCRIPT, d)] = _ent("script")
    elif kind == KIND_THROTTLE:
        s[vol.Required(D_VALUE, default=d.get(D_VALUE, vol.UNDEFINED))] = _ent(["number", "input_number"])
        s[vol.Required(D_MAX_VALUE, default=d.get(D_MAX_VALUE, 100))] = _num(0, 100000, 0.1)
        s[vol.Required(D_MIN_VALUE, default=d.get(D_MIN_VALUE, 30))] = _num(0, 100000, 0.1)
        s[vol.Required(D_STEP, default=d.get(D_STEP, 10))] = _num(0.1, 100000, 0.1)
        s[_opt(D_POWER, d)] = _ent("sensor")
        s[vol.Required(D_POWER_W, default=d.get(D_POWER_W, 0))] = _num(0, 50000, 10, "W")
        s[_opt(D_COMFORT, d)] = _ent("sensor")
        s[vol.Required(D_COMFORT_MIN, default=d.get(D_COMFORT_MIN, 20))] = _num(-50, 1000, 0.5)
        s[vol.Required(D_HOLD, default=d.get(D_HOLD, 0))] = _num(0, 240, 1, "min")
        s[vol.Required(D_PAUSE, default=d.get(D_PAUSE, 0))] = _num(0, 240, 1, "min")
        s[vol.Required(D_MAX_OFF, default=d.get(D_MAX_OFF, 0))] = _num(0, 1440, 1, "min")
    elif kind == KIND_BATTERY:
        s[vol.Required(D_SOC, default=d.get(D_SOC, vol.UNDEFINED))] = _ent("sensor")
        s[vol.Required(D_MIN_SOC, default=d.get(D_MIN_SOC, 30))] = _num(0, 100, 1, "%")
        s[vol.Required(D_REL1, default=d.get(D_REL1, vol.UNDEFINED))] = _ent(RELEASE_DOMAINS)
        s[vol.Required(D_REL1_VALUE, default=d.get(D_REL1_VALUE, vol.UNDEFINED))] = TextSelector()
        s[_opt(D_REL2, d)] = _ent(RELEASE_DOMAINS)
        s[_opt(D_REL2_VALUE, d)] = TextSelector()
        s[vol.Required(D_POWER_W, default=d.get(D_POWER_W, 800))] = _num(10, 20000, 10, "W")
        s[vol.Required(D_MAX_OFF, default=d.get(D_MAX_OFF, 0))] = _num(0, 1440, 1, "min")
        s[vol.Required(D_RESTORE_ORIG, default=d.get(D_RESTORE_ORIG, True))] = BooleanSelector()
        s[_opt(D_OFF_SCRIPT, d)] = _ent("script")
        s[_opt(D_RESERVE_ENTITY, d)] = _ent(RELEASE_DOMAINS)
        s[_opt(D_RESERVE_VALUE, d)] = TextSelector()
        s[vol.Required(D_RESERVE_LEAD, default=d.get(D_RESERVE_LEAD, 60))] = _num(0, 360, 5, "min")
    else:
        s[vol.Required(D_ON_SCRIPT, default=d.get(D_ON_SCRIPT, vol.UNDEFINED))] = _ent("script")
        s[_opt(D_OFF_SCRIPT, d)] = _ent("script")
        s[vol.Required(D_POWER_W, default=d.get(D_POWER_W, 800))] = _num(10, 20000, 10, "W")
        s[vol.Required(D_MAX_OFF, default=d.get(D_MAX_OFF, 0))] = _num(0, 1440, 1, "min")
    s[_opt(D_ALLOW, d)] = _ent(ON_OFF_DOMAINS)
    if kind != KIND_VEHICLE:
        s[vol.Required(D_OBSERVE, default=bool(d.get(D_OBSERVE, False)))] = BooleanSelector()
    return vol.Schema(s)


def device_title(d: dict[str, Any], kind: str | None = None) -> str:
    """One line for the device list on the integration page: priority, name and what the guard does with it."""
    kind = kind or d.get(D_KIND)
    prio = int(d.get(D_PRIORITY, 5))
    if kind == KIND_EVCC:
        what = (f"evcc #{int(d.get(D_EVCC_LOADPOINT, 1))} · {int(d.get(D_MAX_CURRENT, 16))}→{int(d.get(D_MIN_CURRENT, 6))} A"
                + (", 1~" if d.get(D_EVCC_ONE_PHASE) else ""))
    elif kind == KIND_WALLBOX:
        what = f"{int(d.get(D_MAX_CURRENT, 16))}→{int(d.get(D_MIN_CURRENT, 6))} A" + (", 1~" if d.get(D_ONE_PHASE) else "")
    elif kind == KIND_SWITCH:
        what = f"aus ab {int(d.get(D_MIN_POWER, 100))} W" + (f", ≤ {int(d.get(D_MAX_OFF))} min" if d.get(D_MAX_OFF) else "")
    elif kind == KIND_VEHICLE:
        return f"Ladeplan · {d.get(D_NAME, '?')} · bis {int(d.get(D_TARGET_SOC, 80))} % zur Abfahrt"
    elif kind == KIND_SETTING:
        what = f"Einstellung ändern, ≈ {int(d.get(D_POWER_W, 0))} W"
    elif kind == KIND_THROTTLE:
        what = f"{d.get(D_MAX_VALUE, 100):g}→{d.get(D_MIN_VALUE, 0):g}, Schritt {d.get(D_STEP, 5):g}"
    elif kind == KIND_BATTERY:
        what = f"Batterie ab {int(d.get(D_MIN_SOC, 30))} %, ≈ {int(d.get(D_POWER_W, 0))} W"
    else:
        what = f"Skript ≈ {int(d.get(D_POWER_W, 0))} W"
    if d.get(D_OBSERVE):
        what += " · nur beobachten"
    return f"{prio} · {d.get(D_NAME, '?')} · {what}"


class WaechterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,)) or await _grid_source_errors(self.hass, user_input)
            if errors:
                return self.async_show_form(step_id="user", data_schema=_general_schema(user_input, True), errors=errors)
            data = {k: user_input[k] for k in (CONF_GRID_POWER, CONF_GRID_ENERGY, CONF_EVCC_URL, CONF_EVCC_PASSWORD) if user_input.get(k)}
            options = {CONF_LIMIT: user_input[CONF_LIMIT], CONF_MARGIN: user_input[CONF_MARGIN]}
            return self.async_create_entry(title=user_input["name"], data=data, options=options)
        local = await find_local_evcc(self.hass, need_grid=True)
        return self.async_show_form(step_id="user", data_schema=_general_schema({CONF_EVCC_URL: local} if local else {}, True))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WaechterOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            KIND_WALLBOX: WallboxFlow, KIND_EVCC: EvccFlow, KIND_SWITCH: SwitchFlow, KIND_SCRIPT: ScriptFlow, KIND_BATTERY: BatteryFlow,
            KIND_SETTING: SettingFlow, KIND_THROTTLE: ThrottleFlow, KIND_VEHICLE: VehicleFlow,
        }


class WaechterOptionsFlow(OptionsFlow):
    """General settings (gear icon). Devices are subentries on the integration page."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if not current.get(CONF_PLANNER) and not current.get(CONF_CHARGE_PLAN):
            planners = self.hass.config_entries.async_entries("plugwhen")  # offered, not forced
            if len(planners) == 1:
                current[CONF_PLANNER] = planners[0].entry_id
        if user_input is not None:
            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,)) or await _grid_source_errors(self.hass, user_input)
            if errors:
                return self.async_show_form(step_id="init", data_schema=_general_schema({**current, **user_input}, False), errors=errors)
            keep = {k: v for k, v in self.config_entry.options.items() if k in (CONF_LIMIT, CONF_MARGIN)}
            keep.update({k: v for k, v in user_input.items() if v not in (None, "")})
            for cleared in (CONF_GRID_ENERGY, CONF_GRID_POWER, CONF_EVCC_URL, CONF_EVCC_PASSWORD):
                if not user_input.get(cleared):
                    keep[cleared] = ""  # cleared on purpose; overrides the value from set-up
            return self.async_create_entry(data=keep)
        if CONF_EVCC_URL not in current:   # never set (an address cleared on purpose is stored as "" and stays empty)
            local = await find_local_evcc(self.hass, need_grid=True)
            if local:
                current[CONF_EVCC_URL] = local
        return self.async_show_form(step_id="init", data_schema=_general_schema(current, False))


class _DeviceFlow(ConfigSubentryFlow):
    kind: str

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._form(user_input, {})

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._form(user_input, dict(self._get_reconfigure_subentry().data))

    async def _form(self, user_input: dict[str, Any] | None, current: dict[str, Any]) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = unit_errors(self.hass.states.get, user_input, (D_POWER,)) or self._validate(user_input)
            if not errors:
                errors = await self._validate_async(user_input)
            if not errors:
                data = {k: v for k, v in user_input.items() if v not in (None, "")}
                for k in (D_PRIORITY, D_MIN_CURRENT, D_MAX_CURRENT, D_EVCC_LOADPOINT):
                    if k in data:
                        data[k] = int(data[k])
                data[D_KIND] = self.kind
                title = device_title(data)
                if self.source == "user":
                    return self.async_create_entry(title=title, data=data)
                return self.async_update_and_abort(
                    self._get_entry(), self._get_reconfigure_subentry(), title=title, data=data
                )
            current = user_input
        step = "user" if self.source == "user" else "reconfigure"
        return self.async_show_form(step_id=step, data_schema=_device_schema(self.kind, current), errors=errors)

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        return {}

    async def _validate_async(self, u: dict[str, Any]) -> dict[str, str]:
        return {}


class EvccFlow(_DeviceFlow):
    """A loadpoint of evcc: the guard sets evcc's ceiling for the charging current (see evcc.py). Checks the connection when saving."""

    kind = KIND_EVCC

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return await self._form(user_input, {})
        # little to set: the address (and password) of the general settings, else an evcc on this machine
        entry = self._get_entry()
        cfg = {**entry.data, **entry.options}
        current: dict[str, Any] = {}
        if cfg.get(CONF_EVCC_URL):
            current[D_EVCC_URL] = cfg[CONF_EVCC_URL]
            if cfg.get(CONF_EVCC_PASSWORD):
                current[D_EVCC_PASSWORD] = cfg[CONF_EVCC_PASSWORD]
        else:
            local = await find_local_evcc(self.hass)
            if local:
                current[D_EVCC_URL] = local
        return await self._form(None, current)

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        if int(u.get(D_MIN_CURRENT, 6)) > int(u.get(D_MAX_CURRENT, 16)):
            return {D_MIN_CURRENT: "min_above_max"}
        return {}

    async def _validate_async(self, u: dict[str, Any]) -> dict[str, str]:
        client = EvccClient(async_get_clientsession(self.hass), str(u.get(D_EVCC_URL) or ""), u.get(D_EVCC_PASSWORD))
        try:
            state = await client.state()
        except EvccAuthError:
            return {D_EVCC_PASSWORD: "evcc_auth"}
        except EvccError:
            return {D_EVCC_URL: "evcc_unreachable"}
        if parse_loadpoint(state, int(float(u.get(D_EVCC_LOADPOINT) or 1))) is None:
            return {D_EVCC_LOADPOINT: "evcc_loadpoint"}
        return {}


class WallboxFlow(_DeviceFlow):
    kind = KIND_WALLBOX

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        if int(u.get(D_MIN_CURRENT, 6)) > int(u.get(D_MAX_CURRENT, 16)):
            return {D_MIN_CURRENT: "min_above_max"}
        phase, option = u.get(D_PHASE), (u.get(D_ONE_PHASE) or "").strip()
        if bool(phase) != bool(option):
            return {D_ONE_PHASE: "phase_pair"}
        if phase:
            st = self.hass.states.get(phase)
            options = st.attributes.get("options", []) if st else []
            if option not in options:
                return {D_ONE_PHASE: "unknown_option"}
        return {}


class SwitchFlow(_DeviceFlow):
    kind = KIND_SWITCH


class ScriptFlow(_DeviceFlow):
    kind = KIND_SCRIPT

def _validate_pairs(hass, u: dict[str, Any]) -> dict[str, str]:
    """Setting and value belong together; the value must fit the kind of entity."""
    for ent_key, val_key in ((D_REL1, D_REL1_VALUE), (D_REL2, D_REL2_VALUE)):
        ent, val = u.get(ent_key), str(u.get(val_key) or "").strip()
        if bool(ent) != bool(val):
            return {val_key: "pair"}
        if not ent:
            continue
        domain = ent.split(".")[0]
        if domain in ("number", "input_number"):
            try:
                float(val)
            except ValueError:
                return {val_key: "value_number"}
        elif domain in ("select", "input_select"):
            st = hass.states.get(ent)
            options = st.attributes.get("options", []) if st else []
            if options and val not in options:
                return {val_key: "unknown_option"}
        elif val not in ("on", "off"):
            return {val_key: "value_onoff"}
    return {}


class BatteryFlow(_DeviceFlow):
    kind = KIND_BATTERY

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        return _validate_pairs(self.hass, u)


class SettingFlow(_DeviceFlow):
    kind = KIND_SETTING

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        return _validate_pairs(self.hass, u)


class ThrottleFlow(_DeviceFlow):
    kind = KIND_THROTTLE

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        lo, hi, step = float(u.get(D_MIN_VALUE, 0)), float(u.get(D_MAX_VALUE, 100)), float(u.get(D_STEP, 1))
        if lo >= hi:
            return {D_MIN_VALUE: "min_above_max"}
        if step > hi - lo:
            return {D_STEP: "step_too_big"}
        return {}


class VehicleFlow(_DeviceFlow):
    kind = KIND_VEHICLE

    def _validate(self, u: dict[str, Any]) -> dict[str, str]:
        if float(u.get(D_CHARGE_MIN, 1.4)) > float(u.get(D_CHARGE_MAX, 11)):
            return {D_CHARGE_MIN: "min_above_max"}
        for ent_key, val_key in ((D_START, D_START_VALUE), (D_STOP, D_STOP_VALUE)):
            ent, val = u.get(ent_key), str(u.get(val_key) or "").strip()
            if not ent:
                if val:
                    return {val_key: "pair"}
                continue
            domain = ent.split(".")[0]
            if domain == "button":
                continue
            if not val:
                return {val_key: "pair"}
            if domain in ("number", "input_number"):
                try:
                    float(val)
                except ValueError:
                    return {val_key: "value_number"}
            elif domain in ("select", "input_select"):
                st = self.hass.states.get(ent)
                options = st.attributes.get("options", []) if st else []
                if options and val not in options:
                    return {val_key: "unknown_option"}
            elif val not in ("on", "off"):
                return {val_key: "value_onoff"}
        return {}
