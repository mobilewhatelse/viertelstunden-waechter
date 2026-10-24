"""Tests for the decision engine (no Home Assistant needed):  python -m unittest discover tests"""

from __future__ import annotations

import unittest
from datetime import timedelta

from sim import START, House, devices, engine, run


class PeakTests(unittest.TestCase):
    def test_cooker_and_car_stay_below_limit(self):
        house = House(cooker=[(5, 35, 7.0), (10, 25, 3.5)])
        quarters, _ = run(house, engine.Guard(devices()), 90)
        self.assertTrue(all(q <= 10.0 for q in quarters), quarters)
        self.assertGreaterEqual(house.min_current_seen, 6, "the car is never stopped")
        # after cooking: pool and heater back on, car 3-phase with what fits (9.5 kW - 3.15 kW house -> 9 A)
        self.assertTrue(house.pool_on and house.heater_on)
        self.assertEqual((house.current, house.phase_option), (9, "Auto"))

    def test_car_gets_full_current_back_when_there_is_room(self):
        house = House(cooker=[(5, 20, 7.0)], heater=False, pool=False)
        quarters, _ = run(house, engine.Guard(devices()), 60, limit=13.0)
        self.assertTrue(all(q <= 13.0 for q in quarters), quarters)
        self.assertEqual((house.current, house.phase_option), (16, "Auto"))

    def test_without_guard_the_limit_would_be_exceeded(self):
        house = House(cooker=[(5, 35, 7.0)])
        guard = engine.Guard(devices())
        quarters, _ = run(house, guard, 45, limit=99.0)
        self.assertGreater(max(quarters), 10.0)

    def test_comfort_takes_the_cheapest_device(self):
        # 0.6 kW too much; pool is least important -> pool off, car untouched
        house = House(cooker=[(0, 30, 1.5)])
        house.current = 8
        guard = engine.Guard(devices(prio_wb=3, prio_pool=1, prio_heater=2), engine.STRATEGY_COMFORT)
        _, log = run(house, guard, 10)
        self.assertFalse(house.pool_on)
        self.assertEqual(house.current, 8)
        self.assertTrue(any("Pool aus" in x for x in log))

    def test_order_strategy_reduces_wallbox_first(self):
        house = House(cooker=[(0, 30, 1.5)])
        house.current = 8
        guard = engine.Guard(devices(prio_wb=1, prio_pool=2, prio_heater=3), engine.STRATEGY_ORDER)
        run(house, guard, 10)
        self.assertLess(house.current, 8)
        self.assertTrue(house.pool_on)

    def test_max_off_time_is_respected(self):
        house = House(cooker=[(0, 60, 7.0)])
        guard = engine.Guard(devices(prio_wb=9, prio_pool=1, pool_max_off=10.0))
        _, log = run(house, guard, 40)
        off = [x for x in log if "Pool aus" in x]
        back = [x for x in log if "höchste Auszeit" in x]
        self.assertTrue(off and back, log)
        t_off = off[0][:8]
        t_back = back[0][:8]
        self.assertLessEqual(_minutes(t_off, t_back), 10.5)


class SafetyTests(unittest.TestCase):
    def _guard_with_pool_off(self):
        guard = engine.Guard(devices(prio_wb=9, prio_pool=1))
        R = engine.Reading
        readings = {"wb": R(power_w=0.0, current_a=16), "pool": R(power_w=750.0, is_on=True), "heater": R(power_w=0.0, is_on=False)}
        acts = []
        for i in range(6):
            acts += guard.step(START + timedelta(seconds=20 * i), 12.0, None, readings, 10.0, 0.5, True)
        self.assertIn("pool", guard.interventions)
        return guard, readings, acts

    def test_missing_data_gives_everything_back(self):
        guard, readings, _ = self._guard_with_pool_off()
        readings["pool"] = engine.Reading(power_w=0.0, is_on=False)
        acts = []
        for i in range(6, 20):
            acts += guard.step(START + timedelta(seconds=20 * i), None, None, readings, 10.0, 0.5, True)
        self.assertNotIn("pool", guard.interventions)
        self.assertTrue(any(a.kind == "turn_on" and a.device_id == "pool" for a in acts))

    def test_disabled_gives_everything_back(self):
        guard, readings, _ = self._guard_with_pool_off()
        readings["pool"] = engine.Reading(power_w=0.0, is_on=False)
        acts = guard.step(START + timedelta(minutes=3), 12.0, None, readings, 10.0, 0.5, False)
        self.assertTrue(any(a.kind == "turn_on" for a in acts))
        self.assertEqual(guard.interventions, {})

    def test_not_switched_on_again_when_schedule_says_off(self):
        guard, readings, _ = self._guard_with_pool_off()
        readings["pool"] = engine.Reading(power_w=0.0, is_on=False, restore_allowed=False)
        acts = guard.release_all(START + timedelta(minutes=3), readings)
        self.assertFalse(any(a.kind == "turn_on" for a in acts))
        self.assertTrue(any("bleibt aus" in a.text for a in acts))

    def test_counter_jump_is_ignored(self):
        guard = engine.Guard(devices())
        guard.step(START, 2.0, 1000.0, {}, 10.0, 0.5, True)
        guard.step(START + timedelta(seconds=20), 2.0, 1050.0, {}, 10.0, 0.5, True)  # +50 kWh in 20 s
        self.assertLess(guard.energy_kwh, 0.1)

    def test_counter_is_used_when_larger(self):
        guard = engine.Guard(devices())
        guard.step(START, 2.0, 1000.0, {}, 10.0, 0.5, True)
        guard.step(START + timedelta(minutes=5), 2.0, 1001.0, {}, 10.0, 0.5, True)
        self.assertAlmostEqual(guard.energy_kwh, 1.0, places=2)

    def test_finished_quarter_is_reported(self):
        guard = engine.Guard(devices())
        t = START
        for i in range(46):
            guard.step(t + timedelta(seconds=20 * i), 8.0, None, {}, 10.0, 0.5, True)
            if guard.finished_quarter_kw is not None:
                self.assertAlmostEqual(guard.finished_quarter_kw, 8.0, places=1)
                return
        self.fail("no finished quarter reported")


def _minutes(a: str, b: str) -> float:
    h1, m1, s1 = map(int, a.split(":"))
    h2, m2, s2 = map(int, b.split(":"))
    return ((h2 * 3600 + m2 * 60 + s2) - (h1 * 3600 + m1 * 60 + s1)) / 60.0


if __name__ == "__main__":
    unittest.main()
