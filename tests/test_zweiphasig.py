"""Two-phase wallboxes (field case 26.11.2026, release 0.16.0): python -m unittest discover -s tests

A Victron EV Charging Station behind evcc charged a car on TWO phases: about 9 A, 4.3 to 4.5 kW. The guard knew only 1 or 3
phases and counted two as three: minimum 6 A x 3 x 230 V = 4.14 kW, so the wallbox seemed to have only 0.26 kW of headroom
(really 6 A x 2 x 230 V = 2.76 kW, about 1.6 kW of headroom). Just below 4.24 kW it was no lever at all, and with the strategy
"strict order" the battery (priority 3) was released before the wallbox (priority 1).
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from sim import START, engine

D, R = engine.DeviceConfig, engine.Reading
LIMIT, MARGIN = 10.0, 0.5          # target 9.5 kW
GRID = 9.5 + 1.6                   # 1.6 kW too much at the start of the quarter hour


def devices(one_phase: str | None = None):
    return [
        D(id="egolf", name="eGolf", kind="wallbox", priority=1, min_current=6, max_current=16, one_phase_option=one_phase),
        D(id="wb2", name="Wallbox 2", kind="wallbox", priority=2, min_current=6, max_current=16),
        D(id="speicher", name="Speicher", kind="battery", priority=3, power_w=2000, min_soc=30),
        D(id="boiler", name="Boiler", kind="switch", priority=4, min_power_w=300),
    ]


def readings(power_w: float = 4400.0, current_a: float = 9, phases: int | None = 2, phase_option: str | None = None):
    return {
        "egolf": R(power_w=power_w, current_a=current_a, phases=phases, phase_option=phase_option),
        "wb2": R(power_w=0.0, current_a=16, phases=None),
        "speicher": R(releasable=True, soc=80.0),
        "boiler": R(power_w=1200.0, is_on=True),
    }


def first_step(rd, grid=GRID):
    guard = engine.Guard(devices(), engine.STRATEGY_ORDER)
    return guard, guard.step(START, grid, None, rd, LIMIT, MARGIN, True)


class TwoPhaseFieldCase(unittest.TestCase):
    def test_headroom_of_a_two_phase_wallbox(self):
        guard = engine.Guard(devices())
        red = guard._wb_reduction(guard.devices["egolf"], readings()["egolf"], START)
        # 4.4 kW - 6 A x 2 x 230 V (2.76 kW) = 1.64 kW; counted as three phases it was 0.26 kW
        self.assertAlmostEqual(red, 4.4 - 6 * 2 * guard.v1 / 1000.0, places=3)
        self.assertGreater(red, 1.4)

    def test_strict_order_lowers_the_wallbox_first_not_the_battery(self):
        guard, acts = first_step(readings())
        real = [a for a in acts if a.kind != "log"]
        self.assertTrue(real, acts)
        self.assertEqual((real[0].device_id, real[0].kind, real[0].value), ("egolf", "set_current", 6), [a.text for a in acts])
        self.assertNotIn("speicher", guard.interventions)
        self.assertIn("2-phasig", real[0].text)

    def test_strict_order_wallbox_first_also_just_below_the_three_phase_minimum(self):
        # 9 A on two phases is 4.14 kW at 230 V: a power of 4.2 kW is normal. Counted as three phases (4.14 kW at 6 A) that left
        # 0.06 kW, below the 0.1 kW of a lever: the battery came first (the field case)
        guard, acts = first_step(readings(power_w=4200.0))
        real = [a for a in acts if a.kind != "log"]
        self.assertEqual((real[0].device_id, real[0].kind, real[0].value), ("egolf", "set_current", 6), [a.text for a in acts])
        self.assertNotIn("speicher", guard.interventions)

    def test_the_expected_power_after_the_command_counts_two_phases(self):
        guard, _ = first_step(readings())
        pend = guard._pending["egolf"]
        self.assertAlmostEqual(pend["expect_kw"], 6 * 2 * guard.v1 / 1000.0, places=3)

    def test_savings_count_two_phases(self):
        guard, _ = first_step(readings())
        rd = readings(power_w=2800.0, current_a=6)
        # what 9 A allowed (4.14 kW) minus what it draws now (2.8 kW)
        self.assertAlmostEqual(guard._saved_kw(rd), 9 * 2 * guard.v1 / 1000.0 - 2.8, places=2)

    def test_no_switch_to_one_phase_at_two_phases(self):
        guard = engine.Guard(devices(one_phase="1"), engine.STRATEGY_ORDER)
        rd = readings(power_w=2800.0, current_a=6)       # already at the minimum
        acts = []
        for i in range(30):                              # 10 minutes, far longer than TO_ONE_PHASE_AFTER_S
            acts += guard.step(START + timedelta(seconds=20 * i), GRID, None, rd, LIMIT, MARGIN, True)
        self.assertFalse([a for a in acts if a.kind == "set_phase"], [a.text for a in acts])
        self.assertIn("speicher", guard.interventions, "the next lever helps instead")

    def test_observe_only_note_at_two_phases(self):
        dev = D(id="egolf", name="eGolf", kind="wallbox", priority=1, min_current=6, max_current=16, observe_only=True)
        guard = engine.Guard([dev], engine.STRATEGY_ORDER)
        cur, new, one = guard._wb_would(dev, readings()["egolf"], 1.0)
        # 4.4 kW - 1.0 kW = 3.4 kW on two phases: 7 A (three phases would say 6 A, the minimum)
        self.assertEqual((cur, new, one), (9, 7, False))


class OpenFinding(unittest.TestCase):
    """Why the battery came first in the field case: the arithmetic of 0.15.1, step by step (see CHANGELOG 0.16.0)."""

    def test_three_phase_arithmetic_left_no_lever_below_4_24_kw(self):
        # what 0.15.1 did with the eGolf: two phases counted as three. 6 A x 690 V = 4.14 kW, a lever needs 0.1 kW more
        guard = engine.Guard(devices())
        dev = guard.devices["egolf"]
        for kw, lever in ((4.4, True), (4.25, True), (4.2, False), (3.0, False)):
            r = readings(power_w=kw * 1000.0, phases=3)["egolf"]
            self.assertEqual(guard._wb_reduction(dev, r, START) >= 0.1, lever, kw)
            r2 = readings(power_w=kw * 1000.0, phases=2)["egolf"]
            self.assertGreaterEqual(guard._wb_reduction(dev, r2, START), 0.1, kw)   # with two phases it always is one

    def test_a_car_that_stopped_is_no_lever_the_battery_helps(self):
        # unchanged by design: a wallbox drawing less than 1 kW (the car is full) is no lever, even if the 60 s average of the
        # grid still holds its power. Then the next lever of the order is used.
        guard, acts = first_step(readings(power_w=300.0))
        real = [a for a in acts if a.kind != "log"]
        self.assertEqual(real[0].device_id, "speicher", [a.text for a in acts])


class TwoPhaseRelease(unittest.TestCase):
    def _reduced(self):
        guard, _ = first_step(readings())
        self.assertEqual(guard.interventions["egolf"].get("phases"), 2)
        return guard

    def test_more_room_again_counts_two_phases(self):
        guard = self._reduced()
        dev, r = guard.devices["egolf"], readings(power_w=2800.0, current_a=6)["egolf"]
        later = START + timedelta(minutes=3)
        # 1.5 kW of room: (1.5 - 0.15) kW / (2 x 230 V) = 2 more amps (with three phases it was only 1)
        acts = guard._wb_release(dev, r, 1.5, later, False)
        self.assertEqual([(a.kind, a.value) for a in acts if a.kind == "set_current"], [("set_current", 8)])

    def test_little_room_is_enough_for_one_amp_at_two_phases(self):
        guard = self._reduced()
        dev, r = guard.devices["egolf"], readings(power_w=2800.0, current_a=6)["egolf"]
        # 0.7 kW: more than one amp on two phases (0.46 kW + 0.15), less than one on three (0.69 kW + 0.15)
        acts = guard._wb_release(dev, r, 0.7, START + timedelta(minutes=3), False)
        self.assertEqual([a.value for a in acts if a.kind == "set_current"], [7])

    def test_phases_stay_as_at_the_start_of_the_intervention(self):
        guard = self._reduced()
        # the evcc value of the phases may drop out for a cycle: the intervention keeps its two phases
        self.assertEqual(guard._phases(guard.devices["egolf"], readings(phases=None)["egolf"]), 2)

    def test_an_intervention_saved_by_0_15_1_still_works(self):
        guard = engine.Guard(devices())
        guard.load({"interventions": {"egolf": {"since": START.isoformat(), "orig_current": 9, "orig_phase": None,
                                                 "one_phase": False, "switched": False}}})
        dev = guard.devices["egolf"]
        self.assertEqual(guard._phases(dev, readings(phases=2)["egolf"]), 2)   # the source says two
        self.assertEqual(guard._phases(dev, readings(phases=3)["egolf"]), 3)
        self.assertEqual(guard._phases(dev, readings(phases=1)["egolf"]), 3)   # as before: the sensor lags after 1 -> 3
        self.assertEqual(guard._phases(dev, readings(phases=None)["egolf"]), 3)


class OneAndThreePhasesUnchanged(unittest.TestCase):
    """The arithmetic for one and three phases is the one of 0.15.1."""

    def test_three_phases(self):
        guard = engine.Guard(devices())
        dev = guard.devices["egolf"]
        r = readings(power_w=11000.0, current_a=16, phases=3)["egolf"]
        self.assertEqual(guard._phases(dev, r), 3)
        self.assertAlmostEqual(guard._wb_reduction(dev, r, START), 11.0 - 6 * 3 * guard.v1 / 1000.0, places=3)

    def test_unknown_phases_count_as_three(self):
        guard = engine.Guard(devices())
        dev = guard.devices["egolf"]
        r = readings(power_w=11000.0, current_a=16, phases=None)["egolf"]
        self.assertEqual(guard._phases(dev, r), 3)
        self.assertAlmostEqual(guard._wb_reduction(dev, r, START), 11.0 - 6 * 3 * guard.v1 / 1000.0, places=3)

    def test_more_than_three_reported_counts_as_three(self):
        guard = engine.Guard(devices())
        self.assertEqual(guard._phases(guard.devices["egolf"], readings(phases=4)["egolf"]), 3)

    def test_one_phase(self):
        guard = engine.Guard(devices())
        dev = guard.devices["egolf"]
        for ph in (1, 0):
            r = readings(power_w=2070.0, current_a=9, phases=ph)["egolf"]
            self.assertEqual(guard._phases(dev, r), 1)
            self.assertAlmostEqual(guard._wb_reduction(dev, r, START), 2.07 - 6 * guard.v1 / 1000.0, places=3)

    def test_three_phases_first_step_and_release(self):
        guard, acts = first_step(readings(power_w=11000.0, current_a=16, phases=3), grid=9.5 + 3.0)
        real = [a for a in acts if a.kind != "log"]
        # want 3.2 kW less: 7.8 kW / 690 V = 11 A
        self.assertEqual((real[0].device_id, real[0].value), ("egolf", 11))
        self.assertIn("3-phasig", real[0].text)
        self.assertAlmostEqual(guard._pending["egolf"]["expect_kw"], 11 * 3 * guard.v1 / 1000.0, places=3)
        dev, r = guard.devices["egolf"], readings(power_w=7600.0, current_a=11, phases=3)["egolf"]
        acts = guard._wb_release(dev, r, 1.5, START + timedelta(minutes=3), False)
        self.assertEqual([a.value for a in acts if a.kind == "set_current"], [12])   # (1.5 - 0.15) / 0.69 = 1 A

    def test_three_phases_still_switch_to_one_phase(self):
        guard = engine.Guard(devices(one_phase="1 Phase"), engine.STRATEGY_ORDER)
        rd = readings(power_w=4140.0, current_a=6, phases=3)
        acts = []
        for i in range(30):
            acts += guard.step(START + timedelta(seconds=20 * i), GRID, None, rd, LIMIT, MARGIN, True)
        self.assertTrue([a for a in acts if a.kind == "set_phase" and a.value == "1 Phase"], [a.text for a in acts])


if __name__ == "__main__":
    unittest.main()
