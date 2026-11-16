"""A power sensor that reports rarely (cloud) must not turn a late report into 'command not carried out'."""

from __future__ import annotations

import unittest

from sim import House, devices, engine, run


class PowerGapTests(unittest.TestCase):
    def test_median_needs_enough_gaps(self):
        self.assertIsNone(engine.power_gap([]))
        self.assertIsNone(engine.power_gap([60.0, 60.0]))
        self.assertEqual(engine.power_gap([60.0, 180.0, 120.0]), 120.0)
        self.assertEqual(engine.power_gap([10.0, 20.0, 30.0, 400.0]), 25.0)

    def test_wait_is_the_minute_for_fast_or_unknown_sensors(self):
        R = engine.Reading
        self.assertEqual(engine.verify_wait(None), engine.VERIFY_S)
        self.assertEqual(engine.verify_wait(R()), engine.VERIFY_S)
        self.assertEqual(engine.verify_wait(R(power_gap_s=5.0)), engine.VERIFY_S)

    def test_wait_grows_with_a_slow_sensor_but_stays_bounded(self):
        R = engine.Reading
        self.assertEqual(engine.verify_wait(R(power_gap_s=120.0)), 200.0)
        self.assertEqual(engine.verify_wait(R(power_gap_s=900.0)), engine.VERIFY_MAX_S)


class CloudWallboxTests(unittest.TestCase):
    def _run(self, known: bool):
        house = House(cooker=[(5, 40, 7.0)])
        house.wb_report_s = 150
        house.wb_gap_known = known
        guard = engine.Guard(devices())
        _, log = run(house, guard, 40)
        return guard, "\n".join(log)

    def test_late_power_report_is_not_a_miss_once_the_interval_is_known(self):
        guard, text = self._run(True)
        self.assertNotIn("nicht umgesetzt", text)
        self.assertEqual(guard.misses, 0)

    def test_without_the_measured_interval_the_old_check_reports_a_miss(self):
        guard, text = self._run(False)
        self.assertIn("nicht umgesetzt", text)

    def test_a_deaf_cloud_wallbox_is_still_reported(self):
        house = House(cooker=[(5, 40, 7.0)])
        house.wb_report_s, house.wb_gap_known, house.deaf_wb = 150, True, True
        guard = engine.Guard(devices())
        _, log = run(house, guard, 40)
        self.assertIn("Befehl nicht umgesetzt", "\n".join(log))


if __name__ == "__main__":
    unittest.main()
