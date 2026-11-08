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
