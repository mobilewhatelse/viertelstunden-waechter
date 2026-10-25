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
from homeassistant.helpers.selector import (
    EntitySelector, EntitySelectorConfig, NumberSelector, NumberSelectorConfig, NumberSelectorMode,
    SelectSelector, SelectSelectorConfig, TextSelector,
)

from .const import (
    CONF_CONDITION, CONF_GRID_ENERGY, CONF_GRID_POWER, CONF_LIMIT, CONF_LOCK, CONF_MARGIN, CONF_NOTIFY,
    CONF_STARTUP_MODE, D_ALLOW, D_CURRENT, D_KIND, D_MAX_CURRENT, D_MAX_OFF, D_MIN_CURRENT, D_MIN_POWER, D_NAME,
    D_OFF_SCRIPT, D_ON_SCRIPT, D_ONE_PHASE, D_PHASE, D_PHASES, D_POWER, D_POWER_W, D_PRIORITY, D_RESTORE,
    D_SWITCH, DOMAIN, STARTUP_MODES, STARTUP_RESTORE,
)
from .engine import KIND_SCRIPT, KIND_SWITCH, KIND_WALLBOX

ON_OFF_DOMAINS = ["binary_sensor", "input_boolean", "switch"]


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
    s[vol.Required(CONF_GRID_POWER, default=d.get(CONF_GRID_POWER, vol.UNDEFINED))] = _ent("sensor", "power")
    s[_opt(CONF_GRID_ENERGY, d)] = _ent("sensor", "energy")
    if first:
        s[vol.Required(CONF_LIMIT, default=10.0)] = _num(1, 50, 0.1, "kW")
        s[vol.Required(CONF_MARGIN, default=0.5)] = _num(0, 5, 0.1, "kW")
    else:
        s[_opt(CONF_CONDITION, d)] = _ent(ON_OFF_DOMAINS)
        s[_opt(CONF_LOCK, d)] = _ent(ON_OFF_DOMAINS)
        s[_opt(CONF_NOTIFY, d)] = TextSelector()
        s[vol.Required(CONF_STARTUP_MODE, default=d.get(CONF_STARTUP_MODE, STARTUP_RESTORE))] = SelectSelector(
            SelectSelectorConfig(options=STARTUP_MODES, translation_key=CONF_STARTUP_MODE)
        )
    return vol.Schema(s)


def _device_schema(kind: str, d: dict[str, Any]) -> vol.Schema:
    s: dict[Any, Any] = {
        vol.Required(D_NAME, default=d.get(D_NAME, vol.UNDEFINED)): TextSelector(),
        vol.Required(D_PRIORITY, default=d.get(D_PRIORITY, 1 if kind == KIND_WALLBOX else 5 if kind == KIND_SWITCH else 10)): _num(1, 10),
    }
    if kind == KIND_WALLBOX:
        s[vol.Required(D_POWER, default=d.get(D_POWER, vol.UNDEFINED))] = _ent("sensor", "power")
        s[vol.Required(D_CURRENT, default=d.get(D_CURRENT, vol.UNDEFINED))] = _ent(["number", "input_number"])
        s[vol.Required(D_MIN_CURRENT, default=d.get(D_MIN_CURRENT, 6))] = _num(1, 32, 1, "A")
        s[vol.Required(D_MAX_CURRENT, default=d.get(D_MAX_CURRENT, 16))] = _num(1, 63, 1, "A")
        s[_opt(D_PHASE, d)] = _ent(["select", "input_select"])
        s[_opt(D_ONE_PHASE, d)] = TextSelector()
        s[_opt(D_PHASES, d)] = _ent("sensor")
    elif kind == KIND_SWITCH:
        s[vol.Required(D_SWITCH, default=d.get(D_SWITCH, vol.UNDEFINED))] = _ent(["switch", "input_boolean", "light", "fan"])
        s[_opt(D_POWER, d)] = _ent("sensor", "power")
        s[vol.Required(D_MIN_POWER, default=d.get(D_MIN_POWER, 100))] = _num(0, 20000, 10, "W")
        s[vol.Required(D_POWER_W, default=d.get(D_POWER_W, 0))] = _num(0, 20000, 10, "W")
        s[vol.Required(D_MAX_OFF, default=d.get(D_MAX_OFF, 0))] = _num(0, 1440, 1, "min")
        s[_opt(D_RESTORE, d)] = _ent(ON_OFF_DOMAINS)
    else:
        s[vol.Required(D_ON_SCRIPT, default=d.get(D_ON_SCRIPT, vol.UNDEFINED))] = _ent("script")
        s[_opt(D_OFF_SCRIPT, d)] = _ent("script")
        s[vol.Required(D_POWER_W, default=d.get(D_POWER_W, 800))] = _num(10, 20000, 10, "W")
        s[vol.Required(D_MAX_OFF, default=d.get(D_MAX_OFF, 0))] = _num(0, 1440, 1, "min")
    s[_opt(D_ALLOW, d)] = _ent(ON_OFF_DOMAINS)
    return vol.Schema(s)


def device_title(d: dict[str, Any], kind: str | None = None) -> str:
    """One line for the device list on the integration page: priority, name and what the guard does with it."""
    kind = kind or d.get(D_KIND)
    prio = int(d.get(D_PRIORITY, 5))
    if kind == KIND_WALLBOX:
        what = f"{int(d.get(D_MAX_CURRENT, 16))}→{int(d.get(D_MIN_CURRENT, 6))} A" + (", 1~" if d.get(D_ONE_PHASE) else "")
    elif kind == KIND_SWITCH:
        what = f"aus ab {int(d.get(D_MIN_POWER, 100))} W" + (f", ≤ {int(d.get(D_MAX_OFF))} min" if d.get(D_MAX_OFF) else "")
    else:
        what = f"Skript ≈ {int(d.get(D_POWER_W, 0))} W"
    return f"{prio} · {d.get(D_NAME, '?')} · {what}"


class WaechterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = {k: user_input[k] for k in (CONF_GRID_POWER, CONF_GRID_ENERGY) if user_input.get(k)}
            options = {CONF_LIMIT: user_input[CONF_LIMIT], CONF_MARGIN: user_input[CONF_MARGIN]}
            return self.async_create_entry(title=user_input["name"], data=data, options=options)
        return self.async_show_form(step_id="user", data_schema=_general_schema({}, True))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WaechterOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {KIND_WALLBOX: WallboxFlow, KIND_SWITCH: SwitchFlow, KIND_SCRIPT: ScriptFlow}


class WaechterOptionsFlow(OptionsFlow):
    """General settings (gear icon). Devices are subentries on the integration page."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            keep = {k: v for k, v in self.config_entry.options.items() if k in (CONF_LIMIT, CONF_MARGIN)}
            keep.update({k: v for k, v in user_input.items() if v not in (None, "")})
            if not user_input.get(CONF_GRID_ENERGY):
                keep[CONF_GRID_ENERGY] = ""  # cleared on purpose; overrides the value from set-up
            return self.async_create_entry(data=keep)
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
            errors = self._validate(user_input)
            if not errors:
                data = {k: v for k, v in user_input.items() if v not in (None, "")}
                for k in (D_PRIORITY, D_MIN_CURRENT, D_MAX_CURRENT):
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
