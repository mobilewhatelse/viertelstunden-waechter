"""Viertelstunden-Wächter: keeps the quarter-hour peak of the grid import below a limit."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

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
SERVICE_WEEK_REPORT = "send_week_report"
SERVICE_EXPORT = "export_csv"
SERVICE_EXPLAIN = "explain_today"
SERVICE_CORRECT = "correct_quarter"


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_DASHBOARD):
        return

    async def handle_import(call: ServiceCall) -> dict[str, Any]:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries or getattr(entries[0], "runtime_data", None) is None:
            raise ServiceValidationError("The guard is not set up")
        return entries[0].runtime_data.import_history(call.data.get("days", []), call.data.get("months", []))

    async_register_admin_service(
        hass, DOMAIN, SERVICE_IMPORT_HISTORY, handle_import,
        schema=vol.Schema({vol.Optional("days", default=[]): list, vol.Optional("months", default=[]): list}),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_week(call: ServiceCall) -> dict[str, Any]:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries or getattr(entries[0], "runtime_data", None) is None:
            raise ServiceValidationError("The guard is not set up")
        rep = await entries[0].runtime_data.send_week_report(call.data["current_week"], call.data["push"])
        return {k: v for k, v in rep.items() if k != "text"} | {"text": rep["text"]}

    async_register_admin_service(
        hass, DOMAIN, SERVICE_WEEK_REPORT, handle_week,
        schema=vol.Schema({vol.Optional("current_week", default=False): cv.boolean, vol.Optional("push", default=True): cv.boolean}),
        supports_response=SupportsResponse.OPTIONAL,
    )

    def _guard():
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries or getattr(entries[0], "runtime_data", None) is None:
            raise ServiceValidationError("The guard is not set up")
        return entries[0].runtime_data

    async def handle_export(call: ServiceCall) -> dict[str, Any]:
        return await _guard().export_csv(call.data["kind"], call.data["days"], call.data["format"])

    async_register_admin_service(
        hass, DOMAIN, SERVICE_EXPORT, handle_export,
        schema=vol.Schema({
            vol.Optional("kind", default="quarters"): vol.In(["quarters", "days"]),
            vol.Optional("days", default=31): vol.All(vol.Coerce(int), vol.Range(min=1, max=400)),
            vol.Optional("format", default="standard"): vol.In(["standard", "excel_de"]),
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_explain(call: ServiceCall) -> dict[str, Any]:
        return await _guard().explain_today(call.data["push"])

    async_register_admin_service(
        hass, DOMAIN, SERVICE_EXPLAIN, handle_explain,
        schema=vol.Schema({vol.Optional("push", default=False): cv.boolean}),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle_correct(call: ServiceCall) -> dict[str, Any]:
        try:
            return await _guard().correct_quarter(str(call.data["start"]).strip()[:16], float(call.data["kw"]))
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async_register_admin_service(
        hass, DOMAIN, SERVICE_CORRECT, handle_correct,
        schema=vol.Schema({vol.Required("start"): cv.string,
                           vol.Required("kw"): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1000.0))}),
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def handle(call: ServiceCall) -> dict[str, Any]:
        return await _create_dashboard(hass)

    async_register_admin_service(
        hass, DOMAIN, SERVICE_CREATE_DASHBOARD, handle,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )


def _planners(hass: HomeAssistant, entry) -> list[dict[str, Any]]:
    """Charge plans of a car planner chosen in the settings (by config entry: its charge plan and readiness sensors,
    found by unique id; or charge plan entities named by hand). Empty without a planner: the dashboard then shows the
    guard's own plan. Nothing of the planner is imported."""
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    from .const import CONF_CHARGE_PLAN, CONF_PLANNER

    cfg = {**entry.data, **entry.options}
    out: list[dict[str, Any]] = []
    planner_id = cfg.get(CONF_PLANNER)
    if planner_id and hass.config_entries.async_get_entry(planner_id) is not None:
        ents = er.async_entries_for_config_entry(er.async_get(hass), planner_id)
        devices = dr.async_get(hass)
        for e in sorted(ents, key=lambda z: z.entity_id):
            uid = str(e.unique_id)
            if e.domain != "sensor" or not uid.endswith("_charge_plan"):
                continue
            prefix = uid[: -len("charge_plan")]
            ready = next((r.entity_id for r in ents if r.domain == "sensor" and str(r.unique_id) == prefix + "readiness"), None)
            dev = devices.async_get(e.device_id) if e.device_id else None
            out.append({"name": (dev.name_by_user or dev.name) if dev else None, "plan": e.entity_id, "ready": ready})
    manual = cfg.get(CONF_CHARGE_PLAN) or []
    for eid in ([manual] if isinstance(manual, str) else list(manual)):
        if eid and all(p["plan"] != eid for p in out):
            st = hass.states.get(eid)
            out.append({"name": st.name if st else eid, "plan": eid, "ready": None})
    return out


async def _create_dashboard(hass: HomeAssistant) -> dict[str, Any]:
    """Build the dashboard with this installation's entity ids and return it as YAML (also shown as a persistent
    notification) to paste into the raw configuration editor of a new dashboard. It never writes into a dashboard."""
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
    cfg = {**entries[0].data, **entries[0].options}
    if cfg.get("grid_power"):
        ids["grid_power_sensor"] = cfg["grid_power"]
    config = {"views": build_views(ids, hass.config.language, _planners(hass, entries[0]), evcc=bool(cfg.get("evcc_site_url")))}

    text = ha_yaml.dump(config)
    await hass.services.async_call(
        "persistent_notification", "create",
        {"title": entries[0].title, "notification_id": f"{DOMAIN}_dashboard",
         "message": "Paste this into a new dashboard (three dots > Edit > Raw configuration editor):\n\n```yaml\n" + text + "```"},
    )
    return {"yaml": text, "config": config}
