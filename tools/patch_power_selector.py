"""One-off: grid power, grid energy and device power can be any sensor with the right unit, not only sensors with a device class
(kept for the record).

Issue 1: template sensors with unit_of_measurement W but without device_class: power were missing from the list.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "viertelstunden_waechter"


def rw(path, fn):
    s = path.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in s
    s = fn(s.replace("\r\n", "\n"))
    if crlf:
        s = s.replace("\n", "\r\n")
    path.write_text(s, encoding="utf-8", newline="")


def edit(rel, pairs, root=ROOT):
    def fn(s):
        for a, b in pairs:
            assert s.count(a) == 1, (rel, a[:80], s.count(a))
            s = s.replace(a, b)
        return s
    rw(root / rel, fn)


(PKG / "inputs.py").write_text('''"""Checks of the sensors chosen in the dialogs (pure Python, no Home Assistant imports).

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
''', encoding="utf-8", newline="")

edit("custom_components/viertelstunden_waechter/config_flow.py", [
    ("from .engine import KIND_BATTERY,", "from .inputs import unit_errors\nfrom .engine import KIND_BATTERY,"),
    ('''    s[vol.Required(CONF_GRID_POWER, default=d.get(CONF_GRID_POWER, vol.UNDEFINED))] = _ent("sensor", "power")
    s[_opt(CONF_GRID_ENERGY, d)] = _ent("sensor", "energy")
''', '''    # any sensor: a template sensor with the unit W but without a device class is just as good (the unit is checked on saving)
    s[vol.Required(CONF_GRID_POWER, default=d.get(CONF_GRID_POWER, vol.UNDEFINED))] = _ent("sensor")
    s[_opt(CONF_GRID_ENERGY, d)] = _ent("sensor")
'''),
    ('''        if user_input is not None:
            data = {k: user_input[k] for k in (CONF_GRID_POWER, CONF_GRID_ENERGY) if user_input.get(k)}
''', '''        if user_input is not None:
            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,))
            if errors:
                return self.async_show_form(step_id="user", data_schema=_general_schema(user_input, True), errors=errors)
            data = {k: user_input[k] for k in (CONF_GRID_POWER, CONF_GRID_ENERGY) if user_input.get(k)}
'''),
    ('''        if user_input is not None:
            keep = {k: v for k, v in self.config_entry.options.items() if k in (CONF_LIMIT, CONF_MARGIN)}
''', '''        if user_input is not None:
            errors = unit_errors(self.hass.states.get, user_input, (CONF_GRID_POWER,), (CONF_GRID_ENERGY,))
            if errors:
                return self.async_show_form(step_id="init", data_schema=_general_schema({**current, **user_input}, False), errors=errors)
            keep = {k: v for k, v in self.config_entry.options.items() if k in (CONF_LIMIT, CONF_MARGIN)}
'''),
    ('''            errors = self._validate(user_input)
            if not errors:''', '''            errors = unit_errors(self.hass.states.get, user_input, (D_POWER,)) or self._validate(user_input)
            if not errors:'''),
])
s = (PKG / "config_flow.py").read_text(encoding="utf-8", newline="")
n = s.count('_ent("sensor", "power")')
s = s.replace('_ent("sensor", "power")', '_ent("sensor")')
(PKG / "config_flow.py").write_text(s, encoding="utf-8", newline="")
print("device power selectors changed:", n)

TEXT = {
    "strings.json": ("This sensor has no power unit (W, kW or MW). Add unit_of_measurement: W to the template sensor or choose another sensor.",
                     "This sensor has no energy unit (Wh, kWh or MWh). Add unit_of_measurement: kWh to the template sensor or choose another sensor."),
    "translations/en.json": ("This sensor has no power unit (W, kW or MW). Add unit_of_measurement: W to the template sensor or choose another sensor.",
                             "This sensor has no energy unit (Wh, kWh or MWh). Add unit_of_measurement: kWh to the template sensor or choose another sensor."),
    "translations/de.json": ("Dieser Sensor hat keine Leistungseinheit (W, kW oder MW). Ergänzen Sie beim Template-Sensor unit_of_measurement: W oder wählen Sie einen anderen Sensor.",
                             "Dieser Sensor hat keine Energieeinheit (Wh, kWh oder MWh). Ergänzen Sie beim Template-Sensor unit_of_measurement: kWh oder wählen Sie einen anderen Sensor."),
}
for rel, (power, energy) in TEXT.items():
    p = PKG / rel
    raw = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in raw
    d = json.loads(raw)
    err = {"not_power": power, "not_energy": energy}
    d["config"].setdefault("error", {}).update(err)
    d["options"].setdefault("error", {}).update(err)
    for kind in ("wallbox", "switch", "battery"):
        d["config_subentries"][kind].setdefault("error", {}).update({"not_power": power})
    out = json.dumps(d, indent=2, ensure_ascii=False) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    p.write_text(out, encoding="utf-8", newline="")

edit("CHANGELOG.md", [("## Unreleased\n", """## Unreleased

- **Fix (issue 1):** grid power, grid energy and the power sensor of a device can be **any sensor**, also a template sensor with the unit
  `W` but without `device_class: power`. Before, such sensors were missing from the list. Instead of the device class the dialog now checks
  the **unit** when saving (W, kW, MW for power; Wh, kWh, MWh for energy) and says what to add if it is missing.
""")])
print("ok")
