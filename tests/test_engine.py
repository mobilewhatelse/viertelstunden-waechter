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

    def test_deaf_wallbox_is_repeated_reported_and_the_next_lever_is_used(self):
        house = House(cooker=[(5, 40, 7.0)])
        house.deaf_wb = True
        guard = engine.Guard(devices())
        _, log = run(house, guard, 40)
        text = "\n".join(log)
        self.assertIn("Befehl wird wiederholt", text)
        self.assertIn("Befehl nicht umgesetzt", text)
        self.assertGreaterEqual(guard.misses, 1)
        self.assertIn("Pool aus", text, "the next lever must be used while the wallbox is ignored")

    def test_working_devices_are_never_reported(self):
        house = House(cooker=[(5, 35, 7.0), (10, 25, 3.5)])
        guard = engine.Guard(devices())
        _, log = run(house, guard, 90)
        self.assertEqual(guard.misses, 0)
        self.assertNotIn("nicht umgesetzt", "\n".join(log))
        self.assertNotIn("wiederholt", "\n".join(log))

    def test_switch_that_follows_is_not_reported(self):
        house = House(cooker=[(5, 40, 7.0)], car=False)
        guard = engine.Guard(devices(prio_pool=1, prio_heater=2))
        _, log = run(house, guard, 30, verbose=False)
        self.assertEqual(guard.misses, 0)

    def test_forecast_lowers_the_wallbox_early_but_never_switches_off(self):
        # car at 9 A (6.2 kW) + 1.5 kW house = 7.7 kW: below the target, no reason to act without a forecast
        def scenario(reserve):
            house = House(base_kw=1.5, pool=False, heater=False)
            house.current = 9
            guard = engine.Guard(devices())
            _, log = run(house, guard, 10, reserve=reserve)
            return house, "\n".join(log)

        house, text = scenario(None)
        self.assertEqual(text, "")
        self.assertEqual(house.current, 9)
        house, text = scenario(lambda t: (3.0, "Risiko 12.0 kW laut Prognose"))
        self.assertIn("Vorausschauend", text)
        self.assertLess(house.current, 9)
        self.assertGreaterEqual(house.current, 6, "never stopped")
        self.assertEqual(house.phase_option, "Auto", "a forecast alone never switches to 1 phase")
        self.assertNotIn("aus (", text, "no device is switched off because of a forecast")

    def test_forecast_reserve_is_given_back_after_the_risk_window(self):
        house = House(base_kw=1.5, pool=False, heater=False)
        house.current = 9
        guard = engine.Guard(devices())
        run(house, guard, 40, reserve=lambda t: (3.0, "x") if t < 8 else (0.0, ""))
        self.assertGreaterEqual(house.current, 9)

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


class SavingsTests(unittest.TestCase):
    def test_estimated_unguarded_peak_is_higher_than_the_real_one(self):
        # without the guard this evening would be about 21 kW (car 11, cooker 7, pool 0.75, heater 2, base 0.4)
        house = House(cooker=[(5, 55, 7.0)])
        ug: list[float] = []
        quarters, _ = run(house, engine.Guard(devices()), 60, unguarded=ug)
        self.assertLessEqual(max(quarters), 10.0)
        self.assertGreater(max(ug), 15.0, ug)
        self.assertLess(max(ug), 22.0, ug)  # an estimate must not exceed what really would have happened
        self.assertTrue(all(u >= q - 0.2 for u, q in zip(ug, quarters)))

    def test_no_savings_in_observe_mode(self):
        house = House(cooker=[(5, 35, 7.0)])
        guard = engine.Guard(devices())
        guard.real_effect = False
        ug: list[float] = []
        own: list[float] = []
        run(house, guard, 45, limit=10.0, unguarded=ug, finished=own)  # observe: decides, but nothing is changed
        self.assertTrue(guard.interventions, "the guard did decide to intervene")
        self.assertEqual(ug, own, "nothing was saved because nothing was done")

    def test_savings_estimate_is_zero_without_interventions(self):
        guard = engine.Guard(devices())
        guard.step(START, 3.0, None, {}, 10.0, 0.5, True)
        self.assertEqual(guard.values["saved_kw"], 0.0)


class PricingTests(unittest.TestCase):
    def test_monthly_cost(self):
        from pricing import monthly_cost  # noqa: PLC0415

        self.assertAlmostEqual(monthly_cost(9.4, 30.0, 60.0, 10.0), 9.4 * 30.0 / 12)
        self.assertAlmostEqual(monthly_cost(13.1, 30.0, 60.0, 10.0), (10 * 30.0 + 3.1 * 60.0) / 12)
        self.assertEqual(monthly_cost(0.0, 30.0, 60.0, 10.0), 0.0)
        self.assertEqual(monthly_cost(-1.0, 30.0, 60.0, 10.0), 0.0)

    def test_saving_example(self):
        from pricing import monthly_cost  # noqa: PLC0415

        saved = monthly_cost(13.1, 30.0, 60.0, 10.0) - monthly_cost(9.4, 30.0, 60.0, 10.0)
        self.assertGreater(saved, 15.0)


class BatteryTests(unittest.TestCase):
    def test_battery_is_released_last_and_given_back(self):
        # car and cooker: wallbox, pool and heater go first, the battery only helps when nothing else is left
        house = House(cooker=[(5, 35, 7.0)], battery=True)
        guard = engine.Guard(devices(battery=True), engine.STRATEGY_ORDER)
        quarters, log = run(house, guard, 90)
        released = [x for x in log if "Batterie freigegeben" in x]
        self.assertTrue(released, log)
        self.assertFalse(house.bat_released, "given back at the end")
        self.assertTrue(any("wieder wie vorher" in x for x in log))
        first_other = next(i for i, x in enumerate(log) if "Pool aus" in x or "Boiler aus" in x)
        self.assertLess(first_other, log.index(released[0]))

    def test_no_release_below_minimum_soc(self):
        house = House(cooker=[(5, 35, 7.0)], battery=True, soc=20.0)
        _, log = run(house, engine.Guard(devices(battery=True), engine.STRATEGY_ORDER), 40)
        self.assertFalse(any("Batterie freigegeben" in x for x in log), log)

    def test_no_release_when_already_released(self):
        house = House(cooker=[(5, 35, 7.0)], battery=True)
        house.bat_released = True  # e.g. the user already runs it freely
        guard = engine.Guard(devices(battery=True), engine.STRATEGY_ORDER)
        _, log = run(house, guard, 40)
        self.assertFalse(any("Batterie freigegeben" in x for x in log), log)

    def test_released_battery_is_given_back_when_soc_drops(self):
        guard = engine.Guard(devices(battery=True), engine.STRATEGY_ORDER)
        R = engine.Reading
        readings = {"bat": R(soc=80.0, releasable=True)}
        acts = []
        for i in range(6):  # 12 kW import, only the battery is available
            acts += guard.step(START + timedelta(seconds=20 * i), 12.0, None, readings, 10.0, 0.5, True)
        self.assertIn("bat", guard.interventions)
        readings["bat"] = R(soc=25.0, releasable=False)
        acts = guard.step(START + timedelta(seconds=20 * 7), 12.0, None, readings, 10.0, 0.5, True)
        self.assertNotIn("bat", guard.interventions)
        self.assertTrue(any(a.kind == "battery_restore" for a in acts))

    def test_savings_count_the_battery(self):
        house = House(cooker=[(5, 55, 7.0)], battery=True)
        ug: list[float] = []
        own: list[float] = []
        run(house, engine.Guard(devices(battery=True), engine.STRATEGY_ORDER), 60, unguarded=ug, finished=own)
        self.assertGreater(max(ug), max(own))


class ThrottleTests(unittest.TestCase):
    def test_heat_pump_is_throttled_stepwise_and_restored(self):
        # heat pump 3 kW at 100 %, lowest priority number = first: 100 -> ... -> 30 %, never below
        house = House(cooker=[(5, 35, 7.0)], throttle=True, car=False, pool=False, heater=False)
        guard = engine.Guard(devices(throttle_prio=1), engine.STRATEGY_ORDER)
        quarters, log = run(house, guard, 90, limit=9.0, margin=0.5)  # 10.4 kW load; at 30 % the pump needs 0.9 kW
        self.assertTrue(any("Waermepumpe 100 →" in x for x in log), log)
        self.assertGreaterEqual(min(float(x.split("→")[1].split("(")[0]) for x in log if "Waermepumpe" in x and "→" in x and "wieder" not in x), 30.0)
        self.assertEqual(house.thr_value, 100.0, "back to the normal value at the end")
        self.assertLessEqual(max(quarters), 9.0, quarters)

    def test_comfort_guard_prevents_and_ends_throttling(self):
        house = House(cooker=[(5, 35, 7.0)], throttle=True, car=False, pool=False, heater=False, comfort=17.0)
        guard = engine.Guard(devices(throttle_prio=1, min_soc=19.0), engine.STRATEGY_ORDER)
        _, log = run(house, guard, 40, limit=5.0, margin=0.5)
        self.assertFalse(any("Waermepumpe" in x and "→" in x for x in log), "too cold: the heat pump is left alone")

    def test_pause_after_taking_back(self):
        guard = engine.Guard(devices(throttle_prio=1, pause_min=20.0), engine.STRATEGY_ORDER)
        R = engine.Reading
        t = START
        r = {"hp": R(power_w=3000.0, value=100.0)}
        for i in range(4):  # import too high -> throttled
            guard.step(t + timedelta(seconds=20 * i), 7.0, None, r, 5.0, 0.5, True)
            if guard.interventions:
                break
        self.assertIn("hp", guard.interventions)
        guard.release_all(t + timedelta(minutes=2), r, "test")
        self.assertNotIn("hp", guard.interventions)
        later = t + timedelta(minutes=5)
        for i in range(6):
            guard.step(later + timedelta(seconds=20 * i), 7.0, None, r, 5.0, 0.5, True)
        self.assertNotIn("hp", guard.interventions, "pause of 20 minutes after taking back")

    def test_setting_device_acts_like_the_battery(self):
        dev = engine.DeviceConfig(id="hp", name="Waermepumpe", kind="setting", priority=2, power_w=2000)
        guard = engine.Guard([dev], engine.STRATEGY_ORDER)
        R = engine.Reading
        acts = []
        for i in range(8):
            acts += guard.step(START + timedelta(seconds=20 * i), 9.0, None, {"hp": R(releasable=True)}, 5.0, 0.5, True)
        self.assertTrue(any(a.kind == "battery_release" for a in acts))
        self.assertIn("hp", guard.interventions)


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
