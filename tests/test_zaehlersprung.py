"""A counter that stood still and then steps (issue #4, 16.11.2026): the sensor had no values from 02:00 to 06:15, the import
counter then brought the 5 kWh of the whole gap in one step, and the guard recorded 20.23 kW as the day's and the month's peak."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
import engine
from sim import devices

TZ = timezone(timedelta(hours=1))
STEP = timedelta(seconds=20)


def at(h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 11, 16, h, m, s, tzinfo=TZ)


class Run:
    """Feeds the guard like the coordinator does (every 20 seconds) and keeps what every finished quarter hour was."""

    def __init__(self, start: datetime, counter: float | None = 1000.0):
        self.g = engine.Guard(devices())
        self.t, self.true_counter, self.done = start, counter, {}

    def go(self, until: datetime, kw: float | None, *, real_kw: float | None = None, counter: str = "live", every: int = 20):
        """`kw` = what the power sensor says (None = nothing); `real_kw` = what the house really imports (default: the same);
        `counter`: "live" follows the meter, "held" keeps its last value, "none" is not available; `every` = the counter
        reports only every so many seconds."""
        real = kw if real_kw is None else real_kw
        shown = getattr(self, "_shown", self.true_counter)
        while self.t < until:
            self.t += STEP
            if self.true_counter is not None:
                self.true_counter += (real or 0.0) * STEP.total_seconds() / 3600.0
            if counter == "live" and (self.t - at(0)).total_seconds() % every == 0:
                shown = self.true_counter
            self.g._account(self.t, kw, None if counter == "none" or self.true_counter is None else shown)
            if self.g.finished_quarter_kw is not None:
                self.done[self.t.strftime("%H:%M")] = (self.g.finished_quarter_kw, self.g.finished_estimated)
        self._shown = shown


class CounterBacklogTest(unittest.TestCase):
    def _issue4(self, counter_in_gap: str) -> Run:
        r = Run(at(1, 30))
        r.go(at(2, 0), 1.2)                                              # a normal night
        r.go(at(6, 15), None, real_kw=1.2, counter=counter_in_gap)       # the sensor and the counter say nothing for 4 h 15 min
        r.go(at(6, 28), 1.2, counter=counter_in_gap)                     # the power is back, the counter not yet
        r.go(at(7, 0), 1.2)                                              # the counter comes back with the backlog of 5 kWh
        return r

    def test_backlog_of_a_held_counter_is_no_peak(self):
        r = self._issue4("held")
        kw, estimated = r.done["06:30"]
        self.assertTrue(estimated, "the quarter hour with the backlog must not be recorded as a peak")
        self.assertLess(kw, 2.0)
        self.assertLess(max(v for v, est in r.done.values() if not est), 2.0)

    def test_backlog_of_a_counter_that_was_unavailable_is_no_peak(self):
        r = self._issue4("none")
        kw, estimated = r.done["06:30"]
        self.assertTrue(estimated)
        self.assertLess(kw, 2.0)

    def test_the_quarter_hours_after_it_are_measured_again(self):
        r = self._issue4("held")
        kw, estimated = r.done["06:45"]
        self.assertFalse(estimated)
        self.assertAlmostEqual(kw, 1.2, delta=0.1)

    def test_without_the_fix_it_was_a_peak(self):
        # the same run with the detection switched off (as in 0.14: the step is taken as it comes): what the reporter saw
        old = engine.Guard._counter_backlog
        engine.Guard._counter_backlog = lambda *_a: None
        try:
            r = self._issue4("held")
        finally:
            engine.Guard._counter_backlog = old
        kw, estimated = r.done["06:30"]
        self.assertFalse(estimated)
        self.assertGreater(kw, 15.0)

    def test_a_counter_that_rested_while_the_sun_covered_the_house(self):
        # nothing imported for three hours (the import counter stands still), then the cooker: real import, a real value
        r = Run(at(9, 0))
        r.go(at(12, 7), 0.0)
        r.go(at(12, 45), 6.0)
        for q in ("12:15", "12:30", "12:45"):
            self.assertFalse(r.done[q][1], q)
        self.assertAlmostEqual(r.done["12:30"][0], 6.0, delta=0.2)
        self.assertAlmostEqual(r.done["12:15"][0], 6.0 * 8 / 15, delta=0.3)

    def test_a_counter_that_reports_every_five_minutes(self):
        r = Run(at(9, 0))
        r.go(at(10, 0), 4.0, every=300)
        self.assertTrue(r.done)
        for q, (kw, estimated) in r.done.items():
            self.assertFalse(estimated, q)
            self.assertAlmostEqual(kw, 4.0, delta=0.3)

    def test_a_counter_that_reports_every_quarter_hour(self):
        r = Run(at(9, 0))
        r.go(at(11, 0), 4.0, every=900)
        for q, (kw, estimated) in r.done.items():
            self.assertFalse(estimated, q)
            self.assertAlmostEqual(kw, 4.0, delta=0.3)

    def test_a_real_high_quarter_hour_stays_a_peak(self):
        r = Run(at(17, 0))
        r.go(at(18, 0), 11.5)
        kw, estimated = r.done["17:30"]
        self.assertFalse(estimated)
        self.assertAlmostEqual(kw, 11.5, delta=0.3)

    def test_backlog_without_a_power_sensor(self):
        # only the counter: it was away for an hour and comes back in the middle of a quarter hour
        r = Run(at(9, 0))
        r.go(at(10, 0), None, real_kw=3.0)
        r.go(at(11, 5), None, real_kw=3.0, counter="held")
        r.go(at(11, 30), None, real_kw=3.0)
        self.assertTrue(r.done["11:15"][1])
        self.assertFalse(r.done["11:30"][1])
        self.assertAlmostEqual(r.done["11:30"][0], 3.0, delta=0.3)


class RareCounterTest(unittest.TestCase):
    """Review 20.11.2026: a counter that always reports only every 20 to 30 minutes (cloud) is no outage. Before, every step of
    it was taken for a backlog: nearly every quarter hour counted as estimated (no peak), so the real peaks were too low."""

    @staticmethod
    def _rare(start: datetime, until: datetime, kw: float, gaps_min=(20, 30, 25), counter: float = 3000.0):
        g = engine.Guard(devices())
        t, true, shown, done = start, counter, counter, {}
        nxt, i = start, 0
        while t < until:
            t += STEP
            true += kw * STEP.total_seconds() / 3600.0
            if t >= nxt:
                shown, nxt, i = true, t + timedelta(minutes=gaps_min[i % len(gaps_min)]), i + 1
            g._account(t, kw, shown)
            if g.finished_quarter_kw is not None:
                done[t.strftime("%H:%M")] = (g.finished_quarter_kw, g.finished_estimated)
        return g, done

    def test_a_step_of_a_rare_counter_is_no_backlog(self):
        _g, done = self._rare(at(8, 0), at(14, 0), 4.0)
        self.assertGreater(len(done), 20)
        for q, (kw, estimated) in done.items():
            self.assertFalse(estimated, q)
            self.assertAlmostEqual(kw, 4.0, delta=0.3, msg=q)

    def test_a_rare_counter_every_25_minutes_keeps_its_peak(self):
        r = Run(at(8, 0))
        r.go(at(10, 0), 1.0, every=1500)
        r.go(at(10, 30), 8.0, every=1500)       # the real peak of the day
        r.go(at(12, 0), 1.0, every=1500)
        self.assertFalse(r.done["10:15"][1])
        self.assertFalse(r.done["10:30"][1])
        self.assertAlmostEqual(r.done["10:15"][0], 8.0, delta=0.3)
        self.assertAlmostEqual(max(kw for kw, est in r.done.values() if not est), 8.0, delta=0.3)

    def test_without_the_learned_interval_it_was_taken_for_a_backlog(self):
        old = engine.COUNTER_GAP_FACTOR
        engine.COUNTER_GAP_FACTOR = 0.0       # every gap over 20 minutes counts as an outage, as in 0.15.0
        try:
            r = Run(at(8, 0))
            r.go(at(12, 0), 4.0, every=1500)
        finally:
            engine.COUNTER_GAP_FACTOR = old
        self.assertTrue(any(est for _kw, est in r.done.values()))

    def test_a_rare_counter_that_really_fails_is_still_a_backlog(self):
        # learned: about every 25 minutes; then away for three hours while the power sensor goes on
        r = Run(at(6, 0))
        r.go(at(9, 0), 1.0, every=1500)
        r.go(at(12, 10), 1.0, counter="held")
        r.go(at(13, 0), 1.0, every=20)            # back at 12:10 with the backlog, from then on every 20 seconds
        self.assertTrue(r.done["12:15"][1], "the backlog of three hours must not be a peak")
        self.assertFalse(r.done["12:45"][1])
        self.assertLess(max(kw for kw, est in r.done.values() if not est), 1.5)

    def test_issue4_with_the_numbers_of_the_report(self):
        """Issue #4: the counter stood at 2628.5 kWh at 02:00 and at 2632.9 kWh at 06:15, without any power value in between;
        the quarter hour was recorded with 20.23 kW. It must not count as a peak any more."""
        r = Run(at(1, 30), counter=2628.5 - 1.2 * 0.5)
        r.go(at(2, 0), 1.2)
        self.assertAlmostEqual(r.true_counter, 2628.5, places=3)
        r.go(at(6, 15), None, real_kw=4.4 / 4.25, counter="held")    # 02:00 .. 06:15: no power, the counter holds 2628.5
        r.go(at(6, 30), None, real_kw=1.0)                            # the counter is back with 2632.9 kWh, still no power
        r.go(at(7, 0), 1.0)
        self.assertAlmostEqual(r._shown, r.true_counter, places=3)
        kw, estimated = r.done["06:30"]
        self.assertTrue(estimated, "the quarter hour with the backlog of 4.4 kWh must not be recorded as a peak")
        self.assertLess(kw, 2.0)
        self.assertLess(max(v for v, est in r.done.values() if not est), 2.0)


class PlausibleTest(unittest.TestCase):
    def test_bound_follows_the_limit(self):
        self.assertEqual(engine.plausible_kw(5.0), 25.0)
        self.assertEqual(engine.plausible_kw(10.0), 40.0)
        self.assertEqual(engine.plausible_kw(15.0), 60.0)
        self.assertEqual(engine.plausible_kw(40.0), 160.0)
        self.assertEqual(engine.plausible_kw(None), 60.0)
        self.assertEqual(engine.plausible_kw(0), 60.0)

    def test_step_sets_it(self):
        g = engine.Guard(devices())
        g.step(at(9, 0, 20), 1.0, None, {}, 6.0, 0.5, False)
        self.assertEqual(g.max_plausible_kw, 25.0)

    def test_a_jump_above_the_bound_is_not_taken(self):
        # limit 6 kW: 30 kW as a quarter-hour average is no measurement, the power sensor's 2 kW count
        g = engine.Guard(devices())
        g.max_plausible_kw = engine.plausible_kw(6.0)
        t, c = at(9, 0, 0), 500.0
        g._account(t, 2.0, c)
        for _ in range(30):
            t += STEP
            g._account(t, 2.0, c + 7.5)   # 7.5 kWh at once = 30 kW
        self.assertLess(g.energy_kwh, 0.5)


if __name__ == "__main__":
    unittest.main()
