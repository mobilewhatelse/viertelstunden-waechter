"""Questions under Settings > Repairs: share anonymous data? (once after an update) and, for those who shared before 0.15,
one quiet note that the device check sends measured values (keep sharing, or switch it off)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import BooleanSelector

from .const import DOMAIN


def _guards(hass: HomeAssistant):
    return [e.runtime_data for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None) is not None]


class ShareUsageFlow(RepairsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            for w in _guards(self.hass):
                w.answer_usage(bool(user_input.get("share_usage")))
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema(
            {vol.Required("share_usage", default=False): BooleanSelector()}))


class ShareCheckFlow(RepairsFlow):
    """Shared before 0.15: keep sharing (preset, the device check then starts) or switch sharing off."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            for w in _guards(self.hass):
                w.confirm_check(bool(user_input.get("share_usage")))
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema(
            {vol.Required("share_usage", default=True): BooleanSelector()}))


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    return ShareCheckFlow() if issue_id == "share_usage_check" else ShareUsageFlow()
