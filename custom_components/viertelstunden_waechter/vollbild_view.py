"""Charts full screen: the page behind every chart of the dashboard (see vollbild.py)."""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template

from .vollbild import back_path, extract_image, link_charts, page

_LOGGER = logging.getLogger(__name__)


def _data_key(domain: str) -> str:
    return f"{domain}_vollbild"


async def async_setup(hass: HomeAssistant, domain: str, title: str) -> None:
    """Once per start: the key of this installation (kept) and the page."""
    if _data_key(domain) in hass.data:
        return
    store: Store = Store(hass, 1, f"{domain}.vollbild")
    data: dict[str, Any] = await store.async_load() or {}
    if not data.get("key"):
        data["key"] = secrets.token_urlsafe(24)
        await store.async_save(data)
    hass.data[_data_key(domain)] = {"store": store, "data": data}
    if getattr(hass, "http", None) is not None:
        hass.http.register_view(ChartView(domain, title))


async def async_link(hass: HomeAssistant, domain: str, config: dict[str, Any]) -> None:
    """Makes the charts of a freshly built dashboard links to their full-screen pages and keeps the card templates."""
    state = hass.data.get(_data_key(domain))
    if state is None:
        return
    charts = link_charts(config, f"/api/{domain}/vollbild", state["data"]["key"])
    state["data"]["charts"] = charts
    await state["store"].async_save(state["data"])


class ChartView(HomeAssistantView):
    """No login: the app opens the link in the browser. The random key of the installation protects it; a wrong key or an unknown
    chart is simply not found."""

    requires_auth = False

    def __init__(self, domain: str, title: str) -> None:
        self.domain, self.title = domain, title
        self.url = f"/api/{domain}/vollbild/{{key}}/{{chart}}"
        self.name = f"api:{domain}:vollbild"

    async def get(self, request: web.Request, key: str, chart: str) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        state = hass.data.get(_data_key(self.domain))
        if state is None or not hmac.compare_digest(key.encode(), str(state["data"].get("key", "")).encode()):
            return web.Response(status=404)
        tpl = (state["data"].get("charts") or {}).get(chart)
        if tpl is None:
            return web.Response(status=404)
        try:
            rendered = Template(tpl, hass).async_render(parse_result=False)
        except Exception as err:  # noqa: BLE001 - a chart that cannot be drawn right now is an empty page, not an error
            _LOGGER.debug("%s: full-screen chart %s failed: %s", self.domain, chart, err)
            rendered = ""
        return web.Response(
            text=page(self.title, extract_image(str(rendered)), hass.config.language,
                      back_path(request.headers.get("Referer"), request.host)), content_type="text/html",
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex",
                     "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'"})
