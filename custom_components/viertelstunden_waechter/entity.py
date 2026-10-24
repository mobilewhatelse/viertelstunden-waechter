"""Common base for all entities of the guard."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import Waechter


class WaechterEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, waechter: Waechter, key: str) -> None:
        self.waechter = waechter
        self._attr_translation_key = key
        self._attr_unique_id = f"{waechter.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, waechter.entry.entry_id)},
            name=waechter.entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Viertelstunden-Wächter",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, self.waechter.signal, self.async_write_ha_state))
