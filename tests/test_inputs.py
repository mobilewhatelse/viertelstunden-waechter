"""Tests for the unit check of the chosen sensors (issue 1: template sensors without a device class must be usable)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"))

from inputs import unit_errors  # noqa: E402


def states(**units):
    """A fake `hass.states.get`: entity id -> state with that unit (None = a sensor without a unit)."""
    table = {k.replace("__", "."): SimpleNamespace(attributes={"unit_of_measurement": u} if u is not None else {}) for k, u in units.items()}
    return table.get


class UnitErrorsTest(unittest.TestCase):
    def test_a_template_sensor_with_unit_w_and_no_device_class_is_fine(self):
        # the state object carries no device class at all: only the unit counts
        self.assertEqual(unit_errors(states(sensor__power_import="W"), {"grid_power": "sensor.power_import"}, ("grid_power",)), {})

    def test_kw_and_mw_are_power_units(self):
        for unit in ("W", "kW", "MW"):
            self.assertEqual(unit_errors(states(sensor__x=unit), {"grid_power": "sensor.x"}, ("grid_power",)), {}, unit)

    def test_a_power_sensor_without_unit_is_refused(self):
        self.assertEqual(unit_errors(states(sensor__x=None), {"grid_power": "sensor.x"}, ("grid_power",)), {"grid_power": "not_power"})

    def test_a_sensor_with_a_wrong_unit_is_refused(self):
        for unit in ("kWh", "%", "°C", "A", ""):
            self.assertEqual(unit_errors(states(sensor__x=unit), {"grid_power": "sensor.x"}, ("grid_power",)), {"grid_power": "not_power"}, unit)

    def test_energy_units(self):
        for unit in ("Wh", "kWh", "MWh"):
            self.assertEqual(unit_errors(states(sensor__e=unit), {"grid_energy": "sensor.e"}, (), ("grid_energy",)), {}, unit)
        self.assertEqual(unit_errors(states(sensor__e="W"), {"grid_energy": "sensor.e"}, (), ("grid_energy",)), {"grid_energy": "not_energy"})

    def test_a_sensor_that_is_not_loaded_yet_is_not_blocked(self):
        self.assertEqual(unit_errors(states(), {"grid_power": "sensor.later"}, ("grid_power",)), {})

    def test_an_empty_optional_field_is_not_checked(self):
        self.assertEqual(unit_errors(states(), {"grid_power": "sensor.x", "grid_energy": ""}, ("grid_power",), ("grid_energy",)), {})
        self.assertEqual(unit_errors(states(), {}, ("grid_power",), ("grid_energy",)), {})

    def test_both_fields_are_checked_independently(self):
        r = unit_errors(states(sensor__p=None, sensor__e=None), {"grid_power": "sensor.p", "grid_energy": "sensor.e"}, ("grid_power",), ("grid_energy",))
        self.assertEqual(r, {"grid_power": "not_power", "grid_energy": "not_energy"})

    def test_the_three_sensors_of_the_issue_all_pass(self):
        s = states(sensor__power_import="W", sensor__power_export="W", sensor__power_current="W")
        for name in ("power_import", "power_export", "power_current"):
            self.assertEqual(unit_errors(s, {"grid_power": f"sensor.{name}"}, ("grid_power",)), {}, name)


if __name__ == "__main__":
    unittest.main()
