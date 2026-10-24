"""Viertelstunden-Wächter: keeps the quarter-hour peak of the grid import below a limit."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import Waechter

type WaechterEntry = ConfigEntry[Waechter]


async def async_setup_entry(hass: HomeAssistant, entry: WaechterEntry) -> bool:
    waechter = Waechter(hass, entry)
    entry.runtime_data = waechter
    # entities first: mode, limit and strategy restore their last values before the first cycle
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await waechter.async_start()
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WaechterEntry) -> bool:
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload(hass: HomeAssistant, entry: WaechterEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
