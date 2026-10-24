"""Set-up dialog and options: general settings and the list of devices the guard may use."""

from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector, EntitySelectorConfig, NumberSelector, NumberSelectorConfig,
    NumberSelectorMode, SelectOptionDict, SelectSelector, SelectSelectorConfig, TextSelector,
)

from .const import (
    CONF_CONDITION, CONF_DEVICES, CONF_GRID_ENERGY, CONF_GRID_POWER, CONF_LIMIT, CONF_LOCK, CONF_MARGIN,
    CONF_NOTIFY, CONF_STARTUP_MODE, D_ALLOW, D_CURRENT, D_ID, D_KIND, D_MAX_CURRENT, D_MAX_OFF,
    D_MIN_CURRENT, D_MIN_POWER, D_NAME, D_OFF_SCRIPT, D_ON_SCRIPT, D_ONE_PHASE, D_PHASE, D_PHASES, D_POWER,
    D_POWER_W, D_PRIORITY, D_RESTORE, D_SWITCH, DOMAIN, STARTUP_MODES, STARTUP_RESTORE,
)
from .engine import KIND_SCRIPT, KIND_SWITCH, KIND_WALLBOX

ON_OFF_DOMAINS = ["binary_sensor", "input_boolean", "switch"]


def _num(lo: float, hi: float, step: float = 1, unit: str | None = None) -> NumberSelector:
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


class WaechterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = {k: user_input[k] for k in (CONF_GRID_POWER, CONF_GRID_ENERGY) if user_input.get(k)}
            options = {CONF_LIMIT: user_input[CONF_LIMIT], CONF_MARGIN: user_input[CONF_MARGIN], CONF_DEVICES: []}
            return self.async_create_entry(title=user_input["name"], data=data, options=options)
        return self.async_show_form(step_id="user", data_schema=_general_schema({}, True))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return WaechterOptionsFlow()


class WaechterOptionsFlow(OptionsFlow):
    def __init__(self) -> None:
        self._opts: dict[str, Any] | None = None
        self._edit_id: str | None = None

    @property
    def opts(self) -> dict[str, Any]:
        if self._opts is None:
            self._opts = {**self.config_entry.data, **self.config_entry.options}
            self._opts[CONF_DEVICES] = [dict(d) for d in self._opts.get(CONF_DEVICES, [])]
        return self._opts

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(data=self.opts)

    def _device(self, dev_id: str | None) -> dict[str, Any]:
        return next((d for d in self.opts[CONF_DEVICES] if d[D_ID] == dev_id), {})

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["settings", "add_wallbox", "add_switch", "add_script"]
        if self.opts[CONF_DEVICES]:
            menu += ["edit_device", "remove_device"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            for k in (CONF_GRID_ENERGY, CONF_CONDITION, CONF_LOCK, CONF_NOTIFY):
                self.opts.pop(k, None)
            self.opts.update({k: v for k, v in user_input.items() if v not in (None, "")})
            return self._save()
        return self.async_show_form(step_id="settings", data_schema=_general_schema(self.opts, False))

    async def async_step_add_wallbox(self, user_input=None) -> ConfigFlowResult:
        self._edit_id = None
        return await self.async_step_wallbox()

    async def async_step_add_switch(self, user_input=None) -> ConfigFlowResult:
        self._edit_id = None
        return await self.async_step_switch()

    async def async_step_add_script(self, user_input=None) -> ConfigFlowResult:
        self._edit_id = None
        return await self.async_step_script()

    async def async_step_wallbox(self, user_input=None) -> ConfigFlowResult:
        return await self._device_step(KIND_WALLBOX, user_input)

    async def async_step_switch(self, user_input=None) -> ConfigFlowResult:
        return await self._device_step(KIND_SWITCH, user_input)

    async def async_step_script(self, user_input=None) -> ConfigFlowResult:
        return await self._device_step(KIND_SCRIPT, user_input)

    async def _device_step(self, kind: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self._device(self._edit_id)
        if user_input is not None:
            errors = self._validate(kind, user_input)
            if not errors:
                dev = {D_ID: self._edit_id or uuid.uuid4().hex[:8], D_KIND: kind}
                dev.update({k: v for k, v in user_input.items() if v not in (None, "")})
                for k in (D_PRIORITY, D_MIN_CURRENT, D_MAX_CURRENT):
                    if k in dev:
                        dev[k] = int(dev[k])
                devs = [d for d in self.opts[CONF_DEVICES] if d[D_ID] != dev[D_ID]]
                self.opts[CONF_DEVICES] = devs + [dev]
                return self._save()
            current = user_input
        return self.async_show_form(step_id=kind, data_schema=_device_schema(kind, current), errors=errors)

    def _validate(self, kind: str, u: dict[str, Any]) -> dict[str, str]:
        if kind != KIND_WALLBOX:
            return {}
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

    async def async_step_edit_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._edit_id = user_input[D_ID]
            kind = self._device(self._edit_id)[D_KIND]
            return await getattr(self, f"async_step_{kind}")()
        return self.async_show_form(step_id="edit_device", data_schema=vol.Schema({vol.Required(D_ID): self._device_picker(False)}))

    async def async_step_remove_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            gone = set(user_input[D_ID])
            self.opts[CONF_DEVICES] = [d for d in self.opts[CONF_DEVICES] if d[D_ID] not in gone]
            return self._save()
        return self.async_show_form(step_id="remove_device", data_schema=vol.Schema({vol.Required(D_ID): self._device_picker(True)}))

    def _device_picker(self, multiple: bool) -> SelectSelector:
        options = [
            SelectOptionDict(value=d[D_ID], label=f"{d.get(D_NAME, d[D_ID])} ({d[D_KIND]}, Priorität {int(d.get(D_PRIORITY, 5))})")
            for d in sorted(self.opts[CONF_DEVICES], key=lambda x: x.get(D_PRIORITY, 5))
        ]
        return SelectSelector(SelectSelectorConfig(options=options, multiple=multiple))
