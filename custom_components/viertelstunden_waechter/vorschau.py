"""The small animated preview shown with the question about sharing anonymous data (served locally, nothing is loaded from outside)."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

URL = f"/{DOMAIN}/vorschau"
_FLAG = f"{DOMAIN}_vorschau"


async def async_register(hass: HomeAssistant) -> None:
    """Serve the folder `vorschau` under /viertelstunden_waechter/vorschau (once; harmless if the web server is not there)."""
    if hass.data.get(_FLAG) or getattr(hass, "http", None) is None:
        return
    hass.data[_FLAG] = True
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL, str(Path(__file__).parent / "vorschau"), True)])
    except Exception:  # noqa: BLE001 - only a picture; the question works without it
        hass.data[_FLAG] = False
