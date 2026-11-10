"""Tests for 'observe only' per device (user 2026-11-09): the guard says what it would do with the device, sends nothing to it and does
not count it as a lever."""

from __future__ import annotations

import unittest
from dataclasses import replace

from sim import House, devices, engine, run


def with_observed(ids):
    return [replace(d, observe_only=True) if d.id in ids else d for d in devices()]


class ObserveOnlyTests(unittest.TestCase):
    def test_the_option_is_read_from_the_settings(self):
        d = engine.DeviceConfig.from_dict({"id": "x", "kind": "wallbox", "observe_only": True})
        self.assertTrue(d.observe_only)
        self.assertFalse(engine.DeviceConfig.from_dict({"id": "x", "kind": "wallbox"}).observe_only)

    def test_an_observed_wallbox_is_never_changed_but_the_note_is_written(self):
        house = House(cooker=[(5, 35, 7.0)])
        _, log = run(house, engine.Guard(with_observed({"wb"})), 40)
        text = "\n".join(log)
        self.assertEqual(house.current, 16, "nothing is sent to an observed wallbox")
        self.assertIn("Nur beobachten: Wallbox", text)
        self.assertIn("nichts gesendet", text)

    def test_the_note_names_the_step_the_guard_would_take_not_the_whole_lever(self):
        """Seen on 2026-11-10: 2.0 kW too much, the note said 'lowered by 6.5 kW' (down to the minimum); the real wallbox got 16 -> 12 A."""
        import re
        house = House(cooker=[(5, 35, 7.0)])
        _, log = run(house, engine.Guard(with_observed({"wb"})), 40)
        note = next(ln for ln in log if "Nur beobachten: Wallbox" in ln)
        m = re.search(r"von (\d+) A auf (\d+) A begrenzt \(−([\d.]+) kW, ([\d.]+) kW zu viel\)", note)
        self.assertIsNotNone(m, note)
        cur, new, kw, excess = int(m.group(1)), int(m.group(2)), float(m.group(3)), float(m.group(4))
        self.assertEqual(cur, 16)
        self.assertLess(new, cur)
        self.assertGreaterEqual(new, 6)
        self.assertLessEqual(kw, excess + 1e-9, "never more than what is too much")

    def test_the_other_levers_still_work(self):
        house = House(cooker=[(5, 35, 7.0)])
        _, log = run(house, engine.Guard(with_observed({"wb"})), 40)
        self.assertIn("Pool aus", "\n".join(log), "the real levers are used as before")

    def test_the_note_comes_once_per_quarter_hour(self):
        house = House(cooker=[(5, 35, 7.0)])
        _, log = run(house, engine.Guard(with_observed({"wb"})), 40)
        notes = [ln for ln in log if "Nur beobachten" in ln]
        self.assertGreaterEqual(len(notes), 1)
        self.assertLessEqual(len(notes), 3, "40 minutes are at most three quarter hours")

    def test_with_only_observed_devices_nothing_is_switched(self):
        house = House(cooker=[(5, 35, 7.0)])
        guard = engine.Guard(with_observed({"wb", "pool", "heater"}))
        _, log = run(house, guard, 40)
        self.assertEqual(house.current, 16)
        self.assertTrue(house.pool_on and house.heater_on)
        self.assertEqual(guard.interventions, {})
        self.assertTrue(all("Nur beobachten" in ln or "Grenze nicht zu halten" in ln for ln in log), log)

    def test_without_observed_devices_nothing_changes(self):
        h1, log1 = House(cooker=[(5, 35, 7.0)]), None
        _, log1 = run(h1, engine.Guard(devices()), 40)
        self.assertFalse([ln for ln in log1 if "Nur beobachten" in ln])


if __name__ == "__main__":
    unittest.main()
