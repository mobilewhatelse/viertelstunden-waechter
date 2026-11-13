"""Settings > Repairs: the question after an update (share anonymous data?) and, in the mode 'active', devices still on 'observe only'."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import BooleanSelector

from .const import D_OBSERVE, DOMAIN
from .engine import KIND_VEHICLE


class ShareUsageFlow(RepairsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if getattr(entry, "runtime_data", None) is not None:
                    entry.runtime_data.answer_usage(bool(user_input.get("share_usage")))
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema(
            {vol.Required("share_usage", default=False): BooleanSelector()}))


class ObserveOnlyFlow(RepairsFlow):
    """Switch 'observe only' off at all devices that have it (cars are not devices of the guard here). The change goes through the
    subentries like the dialog of the device, so the entry reloads and the issue is checked again."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        entries = self.hass.config_entries.async_entries(DOMAIN)
        subs = [(e, s) for e in entries for s in e.subentries.values() if s.data.get(D_OBSERVE) and s.subentry_type != KIND_VEHICLE]
        if user_input is not None:
            for entry, sub in subs:
                self.hass.config_entries.async_update_subentry(entry, sub, data={**sub.data, D_OBSERVE: False})
            return self.async_create_entry(data={})
        names = ", ".join(str(s.data.get("name") or s.title) for _, s in subs)
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}), description_placeholders={"devices": names})


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    if issue_id == "observe_only_active":
        return ObserveOnlyFlow()
    return ShareUsageFlow()
