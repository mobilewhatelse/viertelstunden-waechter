"""The one question after an update: share the anonymous usage statistics? (Settings > Repairs)"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import BooleanSelector

from .const import DOMAIN


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


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    return ShareUsageFlow()
