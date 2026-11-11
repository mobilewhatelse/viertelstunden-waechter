"""The text field for a feedback (sent with the button next to it)."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WaechterEntry
from .entity import WaechterEntity


async def async_setup_entry(hass: HomeAssistant, entry: WaechterEntry, add: AddEntitiesCallback) -> None:
    add([FeedbackText(entry.runtime_data)])


class FeedbackText(WaechterEntity, TextEntity):
    _attr_icon = "mdi:message-text-outline"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 255
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, w) -> None:
        super().__init__(w, "feedback_text")

    @property
    def native_value(self) -> str:
        return self.waechter.feedback_text

    async def async_set_value(self, value: str) -> None:
        self.waechter.feedback_text = value or ""
        self.async_write_ha_state()
