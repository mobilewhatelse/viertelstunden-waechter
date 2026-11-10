"""Tests for the helpers of the set-up assistant: the sign of a power sensor, the highest quarter hour, the evcc takeover."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"))

from inputs import grid_sign_hint, loadpoint_choices, loadpoint_prefill, looks_inverted, quarter_peak  # noqa: E402


class GridSignTest(unittest.TestCase):
    def test_import_negative_at_night_means_invert(self):
        r = grid_sign_hint([(h, -0.4) for h in range(0, 5)] * 2 + [(13, 3.0)] * 5)   # the day (export) does not count
        self.assertEqual((r["verdict"], r["night_kw"], r["n"]), ("invert", -0.4, 10))

    def test_right_sign(self):
        self.assertEqual(grid_sign_hint([(2, 0.3)] * 8)["verdict"], "ok")

    def test_not_enough_or_unclear(self):
        self.assertIsNone(grid_sign_hint([(2, -0.4)] * 3)["verdict"])          # too few night samples
        self.assertIsNone(grid_sign_hint([(12, -2.0)] * 50)["verdict"])        # only daytime: export is normal then
        self.assertIsNone(grid_sign_hint([(1, 0.01)] * 10)["verdict"])         # around zero: nothing to say


class DeviceSignTest(unittest.TestCase):
    def test_consumer_with_negative_values(self):
        self.assertTrue(looks_inverted([-3.5, -3.6, -1.2, 0.0, -2.0, -2.2]))
        self.assertFalse(looks_inverted([3.5, 3.6, 1.2, 0.0, 2.0]))
        self.assertFalse(looks_inverted([-3.5, -3.6]))                         # too few
        self.assertFalse(looks_inverted([0.0, 0.01, -0.02] * 10))              # standby noise


class PeakTest(unittest.TestCase):
    def test_highest_quarter_mean(self):
        t0 = datetime(2026, 11, 9, 18, 0)
        pts = [(t0 + timedelta(minutes=5 * i), v) for i, v in enumerate([1, 1, 1, 9, 9, 6, 2, 2, 2])]
        self.assertEqual(quarter_peak(pts), 8.0)
        self.assertIsNone(quarter_peak([]))
        self.assertEqual(quarter_peak([(t0, -5.0), (t0 + timedelta(minutes=5), -5.0)]), 0.0)   # export is no peak


class EvccTakeoverTest(unittest.TestCase):
    STATE = {"loadpoints": [
        {"title": "Carport", "minCurrent": 6, "maxCurrent": 16, "chargerPhases1p3p": True},
        {"title": "Garage", "minCurrent": 8, "maxCurrent": 32, "chargerPhases1p3p": False},
    ]}

    def test_choices(self):
        self.assertEqual(loadpoint_choices(self.STATE), [(1, "Carport"), (2, "Garage")])
        self.assertEqual(loadpoint_choices(None), [])

    def test_prefill(self):
        self.assertEqual(loadpoint_prefill(self.STATE, 1), {"name": "Carport", "evcc_loadpoint": 1, "min_current": 6, "max_current": 16})
        p = loadpoint_prefill(self.STATE, 2)
        self.assertEqual((p["name"], p["min_current"], p["max_current"], p["evcc_one_phase"]), ("Garage", 8, 32, False))
        self.assertEqual(loadpoint_prefill(self.STATE, 3), {})


if __name__ == "__main__":
    unittest.main()
