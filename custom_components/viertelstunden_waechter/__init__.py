"""Viertelstunden-Wächter: keeps the quarter-hour peak of the grid import below a limit."""

from __future__ import annotations

from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICES, D_ID, D_KIND, D_NAME, PLATFORMS
from .coordinator import Waechter

type WaechterEntry = ConfigEntry[Waechter]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 kept the devices in the options; version 2 has them as subentries."""
    if entry.version == 1:
        options = dict(entry.options)
        for d in options.pop(CONF_DEVICES, []):
            data = {k: v for k, v in d.items() if k != D_ID}
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType(data), subentry_type=d[D_KIND], title=d.get(D_NAME) or d[D_ID], unique_id=None
                ),
            )
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WaechterEntry) -> bool:
    from .config_flow import device_title  # imported here: config_flow pulls in the selector helpers

    for sub in list(entry.subentries.values()):  # keep the list titles current (before the update listener exists)
        title = device_title(dict(sub.data), sub.subentry_type)
        if sub.title != title:
            hass.config_entries.async_update_subentry(entry, sub, title=title)
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
