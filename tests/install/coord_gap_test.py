"""The guard measures how often a device's power sensor reports a new value (0.15) - the coordinator's own method
with a fake Home Assistant state machine. Needs Home Assistant installed, so it runs in its Docker image:

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/coord_gap_test.py
"""

from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import coordinator as co  # noqa: E402

PW = "sensor.wallbox_power"
T0 = datetime(2026, 11, 15, 18, 0)


def make():
    w = object.__new__(co.Waechter)
    w._pw_seen = {}
    w.st = types.SimpleNamespace(state="5800", last_changed=T0, attributes={})
    w._state = lambda eid: w.st if eid == PW else None
    return w


def tick(w, changed_after_s: float | None, kw: float) -> float | None:
    """One cycle; the sensor got a new value `changed_after_s` seconds after the previous one (None: unchanged)."""
    if changed_after_s is not None:
        w.st = types.SimpleNamespace(state=str(kw * 1000), last_changed=w.st.last_changed + timedelta(seconds=changed_after_s),
                                     attributes={})
    return w._power_gap("wb", PW, kw)


class GapTests(unittest.TestCase):
    def test_a_cloud_sensor_is_measured_after_three_new_values(self):
        w = make()
        self.assertIsNone(tick(w, None, 5.8))           # first sight: nothing to compare
        self.assertIsNone(tick(w, None, 5.8))           # unchanged cycles add nothing
        self.assertIsNone(tick(w, 150, 5.8))
        self.assertIsNone(tick(w, 140, 5.9))
        self.assertEqual(tick(w, 160, 6.0), 150.0)
        self.assertEqual(tick(w, None, 6.0), 150.0)     # stays known between new values

    def test_gaps_while_the_device_is_off_do_not_count(self):
        w = make()
        tick(w, None, 0.0)
        for _ in range(4):
            tick(w, 900, 0.0)                           # standby: the sensor rarely changes, says nothing about reporting
        self.assertEqual(w._pw_seen["wb"]["gaps"], [])

    def test_only_the_last_gaps_are_kept(self):
        w = make()
        tick(w, None, 5.0)
        for s in (300, 300, 300, 10, 10, 10, 10, 10, 10):
            tick(w, s, 5.0)
        self.assertEqual(len(w._pw_seen["wb"]["gaps"]), co.POWER_GAP_KEEP)
        self.assertEqual(tick(w, None, 5.0), 10.0)

    def test_no_sensor_no_measurement(self):
        w = make()
        self.assertIsNone(w._power_gap("wb", None, None))
        self.assertIsNone(w._power_gap("wb", "sensor.missing", 1.0))


if __name__ == "__main__":
    unittest.main()
