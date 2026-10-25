"""Diagnostics download: configuration, current values, interventions and the recent log."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import WaechterEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: WaechterEntry) -> dict[str, Any]:
    w = entry.runtime_data
    return {
        "configuration": w.configuration(),
        "mode": w.mode,
        "strategy": w.guard.strategy,
        "limit_kw": w.limit_kw,
        "margin_kw": w.margin_kw,
        "status": w.status,
        "values": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in w.guard.values.items()},
        "interventions": w.guard.interventions,
        "month_peak": w.month_peak,
        "day_peaks": w.day_peaks,
        "log": w.log[:50],
    }
