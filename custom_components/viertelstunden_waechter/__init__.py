"""Viertelstunden-Wächter: keeps the quarter-hour peak of the grid import below a limit."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import CONF_DEVICES, D_ID, D_KIND, D_NAME, DOMAIN, PLATFORMS
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
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WaechterEntry) -> bool:
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload(hass: HomeAssistant, entry: WaechterEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


SERVICE_CREATE_DASHBOARD = "create_dashboard"
SERVICE_IMPORT_HISTORY = "import_history"


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_DASHBOARD):
        return

    async def handle_import(call: ServiceCall) -> dict[str, Any]:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries or getattr(entries[0], "runtime_data", None) is None:
            raise ServiceValidationError("The guard is not set up")
        return entries[0].runtime_data.import_history(call.data.get("days", []), call.data.get("months", []))

    hass.services.async_register(
        DOMAIN, SERVICE_IMPORT_HISTORY, handle_import,
        schema=vol.Schema({vol.Optional("days", default=[]): list, vol.Optional("months", default=[]): list}),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle(call: ServiceCall) -> dict[str, Any]:
        return await _create_dashboard(hass, call.data.get("dashboard"))

    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_DASHBOARD, handle,
        schema=vol.Schema({vol.Optional("dashboard"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )


async def _create_dashboard(hass: HomeAssistant, url_path: str | None) -> dict[str, Any]:
    """Build the dashboard with this installation's entity ids; save it into an existing storage dashboard or
    return it as YAML (also as a persistent notification) to paste into the raw configuration editor."""
    from homeassistant.helpers import entity_registry as er
    from homeassistant.util import yaml as ha_yaml

    from .dashboard import ENTITY_KEYS, build_views

    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("The guard is not set up")
    registry = er.async_get(hass)
    ids: dict[str, str] = {}
    for key, domain in ENTITY_KEYS.items():
        entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entries[0].entry_id}_{key}")
        if entity_id is None:
            raise ServiceValidationError(f"Entity '{key}' not found - restart Home Assistant after the update")
        ids[key] = entity_id
    config = {"views": build_views(ids, hass.config.language)}

    if url_path:
        try:
            from homeassistant.components.lovelace.const import LOVELACE_DATA

            dashboard = hass.data[LOVELACE_DATA].dashboards.get(url_path)
        except (ImportError, KeyError, AttributeError):
            dashboard = None
        if dashboard is None or not hasattr(dashboard, "async_save"):
            raise ServiceValidationError(
                f"Dashboard '{url_path}' not found or not a storage dashboard. Create an empty dashboard first "
                "(Settings > Dashboards > Add) or call the service without a dashboard to get the YAML."
            )
        await dashboard.async_save(config)
        return {"saved": url_path, "views": [v["title"] for v in config["views"]]}

    text = ha_yaml.dump(config)
    await hass.services.async_call(
        "persistent_notification", "create",
        {"title": entries[0].title, "notification_id": f"{DOMAIN}_dashboard",
         "message": "Paste this into a new dashboard (three dots > Edit > Raw configuration editor):\n\n```yaml\n" + text + "```"},
    )
    return {"yaml": text}
