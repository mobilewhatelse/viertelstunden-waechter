"""Wallbox whose charging current is a list (select '6 A', '8 A' ...), e.g. Anker SOLIX V1 (0.14.3)."""

from __future__ import annotations

import unittest

from sim import House, devices, engine, run

STEPS = (6, 8, 10, 12, 14, 16)


class WallboxListTests(unittest.TestCase):
    def test_amps_are_read_from_the_entries(self):
        for text, amps in (("8 A", 8), ("8A", 8), ("16", 16), ("10,0 A", 10), ("6.0 A", 6), ("Max 32 A", 32), ("aus", None)):
            self.assertEqual(engine.amps_of(text), amps, text)

    def test_phases_in_front_are_not_the_current(self):   # 0.15.1: '3x16 A' gave 3 (the first number)
        for text, amps, phases in (("6 A", 6, None), ("8 A", 8, None), ("3x16 A", 16, 3), ("1x16 A", 16, 1), ("16A", 16, None),
                                   ("3 x 10 A", 10, 3), ("3×16A", 16, 3), ("1X6 A", 6, 1), ("3x6,0 A", 6, 3)):
            self.assertEqual(engine.amps_of(text), amps, text)
            self.assertEqual(engine.phases_of(text), phases, text)

    def test_a_list_with_phases_offers_the_currents(self):
        options = ["1x6 A", "1x10 A", "1x16 A", "3x6 A", "3x10 A", "3x16 A"]
        self.assertEqual(sorted({engine.amps_of(o) for o in options}), [6, 10, 16])

    def test_lowering_keeps_the_phase_count_of_the_present_entry(self):
        options = ["1x6 A", "1x10 A", "1x16 A", "3x6 A", "3x10 A", "3x16 A"]
        self.assertEqual(engine.pick_option(options, 10, "3x16 A"), "3x10 A")
        self.assertEqual(engine.pick_option(options, 6, "1x16 A"), "1x6 A")
        self.assertEqual(engine.pick_option(options, 10, None), "1x10 A")       # unknown: the first entry, as before
        self.assertEqual(engine.pick_option(["6 A", "8 A", "16 A"], 8, "16 A"), "8 A")
        self.assertIsNone(engine.pick_option(options, 8, "3x16 A"))

    def test_target_from_a_list_or_number(self):   # Fordpass: select '50'..'100', shown as '80%'; 'Unsupported' without target
        for text, pct in (("80", 80.0), ("80.0", 80.0), ("80%", 80.0), ("80 %", 80.0), ("72,5", 72.5), ("100", 100.0),
                          ("Unsupported", None), ("unknown", None), ("0", None), ("150", None), ("", None)):
            self.assertEqual(engine.percent_of(text), pct, text)

    def test_step_down_never_goes_above_the_wanted_current(self):
        self.assertEqual(engine.step_down(9, STEPS), 8)
        self.assertEqual(engine.step_down(8, STEPS), 8)
        self.assertEqual(engine.step_down(5, STEPS), 6)   # below the lowest entry: the lowest
        self.assertEqual(engine.step_down(20, STEPS), 16)
        self.assertEqual(engine.step_down(9, None), 9)    # a number entity: every whole amp

    def test_peak_kept_with_list_and_only_entries_of_the_list_are_sent(self):
        house = House(cooker=[(5, 35, 7.0), (10, 25, 3.5)])
        house.wb_steps = STEPS
        guard = engine.Guard(devices())
        quarters, log = run(house, guard, 90)
        self.assertTrue(all(q <= 10.0 for q in quarters), quarters)
        self.assertTrue(house.wb_commands, "the wallbox must be lowered")
        self.assertTrue(all(c in STEPS for c in house.wb_commands), house.wb_commands)
        self.assertEqual(guard.misses, 0)
        self.assertNotIn("nicht umgesetzt", "\n".join(log))

    def test_raising_sends_no_command_that_changes_nothing(self):
        def repeats(steps):   # the same current twice in a row; the switch back to 3-phase sends it on purpose (number wallbox too)
            house = House(cooker=[(5, 35, 7.0), (10, 25, 3.5)])
            house.wb_steps = steps
            run(house, engine.Guard(devices()), 90)
            return sum(1 for x, y in zip(house.wb_commands, house.wb_commands[1:]) if x == y), house.wb_commands
        with_list, cmds = repeats(STEPS)
        self.assertLessEqual(with_list, repeats(None)[0], cmds)

    def test_list_that_starts_above_the_minimum_current(self):
        """Minimum 6 A, but the list starts at 8 or 10 A: the lowest entry is the minimum. Before, the guard waited for a
        step the wallbox does not have, other devices did not help and the peak went to 15 kW."""
        for steps in ((8, 10, 13, 16), (10, 13, 16)):
            house = House(cooker=[(5, 35, 7.0), (10, 25, 3.5)])
            house.wb_steps = steps
            guard = engine.Guard(devices())
            quarters, _log = run(house, guard, 90)
            self.assertTrue(all(q <= 10.0 for q in quarters), (steps, quarters))
            self.assertTrue(all(c in steps for c in house.wb_commands), (steps, house.wb_commands))
            self.assertEqual(guard.misses, 0)

    def test_number_wallbox_unchanged(self):
        house = House(cooker=[(5, 35, 7.0), (10, 25, 3.5)])
        run(house, engine.Guard(devices()), 90)
        self.assertEqual((house.current, house.phase_option), (9, "Auto"))


if __name__ == "__main__":
    unittest.main()
