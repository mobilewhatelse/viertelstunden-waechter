"""Checks of the sensors chosen in the dialogs (pure Python, no Home Assistant imports).

A power or energy sensor does not need a device class: a template sensor with `unit_of_measurement: W` is just as good, and many
installations have exactly that. What matters is the unit, because the guard converts it (W, kW, MW; Wh, kWh, MWh).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

POWER_UNITS = ("W", "kW", "MW")
ENERGY_UNITS = ("Wh", "kWh", "MWh")


def unit_errors(
    get_state: Callable[[str], Any],
    values: dict[str, Any],
    power_keys: Iterable[str] = (),
    energy_keys: Iterable[str] = (),
) -> dict[str, str]:
    """Field name -> error key for every chosen sensor whose unit is not a power or energy unit.

    A sensor that is not loaded yet is not blocked (it may come up a moment later); an empty field is not checked."""
    errors: dict[str, str] = {}
    for keys, units, error in ((power_keys, POWER_UNITS, "not_power"), (energy_keys, ENERGY_UNITS, "not_energy")):
        for key in keys:
            entity_id = values.get(key)
            if not entity_id:
                continue
            state = get_state(entity_id)
            if state is None:
                continue
            unit = str(state.attributes.get("unit_of_measurement") or "").strip()
            if unit not in units:
                errors[key] = error
    return errors


# ---------- the sign of a power sensor ----------

NIGHT_HOURS = (0, 5)          # local hours without sun: a grid sensor must show import (positive) then
SIGN_MIN_SAMPLES = 6
SIGN_DEADBAND_KW = 0.05


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def grid_sign_hint(samples: Iterable[tuple[int, float]]) -> dict[str, Any]:
    """Does a grid sensor count import as negative? `samples` = (local hour, kW) of the last nights. At night there is no sun, so
    the house can only draw from the grid: a median clearly below 0 means the sign is the other way round.
    Returns {"night_kw": median or None, "n": samples used, "verdict": "invert" | "ok" | None (not enough to say)}."""
    night = [float(v) for h, v in samples if NIGHT_HOURS[0] <= int(h) < NIGHT_HOURS[1]]
    if len(night) < SIGN_MIN_SAMPLES:
        return {"night_kw": None, "n": len(night), "verdict": None}
    med = _median(night)
    verdict = "invert" if med < -SIGN_DEADBAND_KW else "ok" if med > SIGN_DEADBAND_KW else None
    return {"night_kw": round(med, 3), "n": len(night), "verdict": verdict}


def looks_inverted(values: Iterable[float], min_samples: int = 5, share: float = 0.8) -> bool:
    """A consumer (wallbox, pump) never feeds in: if nearly all clearly non-zero readings are negative, the sign is reversed."""
    nz = [float(v) for v in values if abs(float(v)) > SIGN_DEADBAND_KW]
    return len(nz) >= min_samples and sum(1 for v in nz if v < 0) >= share * len(nz)


def quarter_peak(points: Iterable[tuple[Any, float]]) -> float | None:
    """The highest quarter-hour mean (kW) from (time, kW) points of five-minute means: three in a row make a quarter hour."""
    buckets: dict[Any, list[float]] = {}
    for t, v in points:
        key = t.replace(minute=t.minute - t.minute % 15, second=0, microsecond=0)
        buckets.setdefault(key, []).append(max(0.0, float(v)))
    full = [sum(v) / len(v) for v in buckets.values() if len(v) >= 2]
    return round(max(full), 2) if full else None


# ---------- taking an evcc loadpoint over ----------

def loadpoint_choices(state: dict[str, Any] | None) -> list[tuple[int, str]]:
    """(number 1.., title) of every loadpoint evcc reports."""
    lps = (state or {}).get("loadpoints")
    if not isinstance(lps, list):
        return []
    return [(i, str(lp.get("title") or lp.get("name") or f"#{i}")) for i, lp in enumerate(lps, 1) if isinstance(lp, dict)]


def loadpoint_prefill(state: dict[str, Any] | None, number: int) -> dict[str, Any]:
    """What the device dialog can take over from evcc for loadpoint `number`: its name, the currents and whether it can switch
    to one phase (only offered if the charger can). Empty when the loadpoint does not exist."""
    lps = (state or {}).get("loadpoints")
    if not isinstance(lps, list) or number < 1 or number > len(lps) or not isinstance(lps[number - 1], dict):
        return {}
    lp = lps[number - 1]
    out: dict[str, Any] = {"name": str(lp.get("title") or lp.get("name") or f"evcc {number}"), "evcc_loadpoint": number}
    for key, field in (("minCurrent", "min_current"), ("maxCurrent", "max_current")):
        try:
            v = int(round(float(lp.get(key))))
        except (TypeError, ValueError):
            continue
        if 6 <= v <= 32:
            out[field] = v
    if not lp.get("chargerPhases1p3p"):
        out["evcc_one_phase"] = False
    return out
