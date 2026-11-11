"""A reload or restart in the middle of a quarter hour (seen on 2026-11-10 19:27): the guard had released the wallbox when it stopped,
started again at 12.7 kW and took that for the whole quarter hour: 10.8 kW recorded as the month's peak, a false "limit cannot be
kept", the wallbox down to 6 A. The meter said 8.4 kW."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
import engine
from sim import devices

TZ = timezone(timedelta(hours=1))
Q = datetime(2026, 11, 10, 19, 15, tzinfo=TZ)


def tick(g, t, kw, counter=None):
    g._account(t, kw, counter)


class ResumeTest(unittest.TestCase):
    def before(self, counter=True):
        """12 minutes 40 at 8.4 kW, then the guard stops."""
        g = engine.Guard(devices())
        c = 5000.0
        tick(g, Q - timedelta(seconds=20), 8.4, c if counter else None)
        t = Q
        while t <= Q + timedelta(minutes=12, seconds=40):
            c += 8.4 * 20 / 3600.0 if t > Q else 8.4 * 20 / 3600.0
            tick(g, t, 8.4, c if counter else None)
            t += timedelta(seconds=20)
        return g, c, t - timedelta(seconds=20)

    def test_with_the_counter_the_quarter_hour_is_exact(self):
        g, c, stop = self.before()
        state = g.quarter_state()
        new = engine.Guard(devices())
        new.resume_quarter(state)
        now = stop + timedelta(seconds=60)                       # a minute away, the released wallbox draws 12.7 kW
        c += 12.7 * 60 / 3600.0
        tick(new, now, 12.7, c)
        self.assertFalse(new.quarter_estimated)
        self.assertAlmostEqual(new.energy_kwh, c - state["counter_at_q"], places=3)
        self.assertLess(new.energy_kwh / ((now - Q).total_seconds() / 3600.0), 9.0, "the average so far is about 8.7, not 12.7")

    def test_without_a_counter_only_the_gap_is_guessed(self):
        g, _, stop = self.before(counter=False)
        new = engine.Guard(devices())
        new.resume_quarter(g.quarter_state())
        tick(new, stop + timedelta(seconds=60), 12.7, None)
        self.assertAlmostEqual(new.energy_kwh, g.energy_kwh + 12.7 * 60 / 3600.0, places=3)
        self.assertFalse(new.quarter_estimated)

    def test_another_quarter_hour_is_not_continued(self):
        g, _, _ = self.before()
        new = engine.Guard(devices())
        new.resume_quarter(g.quarter_state())
        tick(new, Q + timedelta(minutes=20), 5.0, None)
        self.assertAlmostEqual(new.energy_kwh, 5.0 * 5 / 60, places=3)
        self.assertTrue(new.quarter_estimated)

    def test_a_guessed_quarter_hour_is_marked_and_the_next_one_is_not(self):
        g = engine.Guard(devices())
        tick(g, Q + timedelta(minutes=12, seconds=40), 12.7, None)      # nothing to continue: the old guess
        self.assertTrue(g.quarter_estimated)
        tick(g, Q + timedelta(minutes=15, seconds=5), 8.4, None)
        self.assertIsNotNone(g.finished_quarter_kw)
        self.assertTrue(g.finished_estimated, "its value must not become a peak")
        self.assertFalse(g.quarter_estimated)
        tick(g, Q + timedelta(minutes=30, seconds=5), 8.4, None)
        self.assertFalse(g.finished_estimated)

    def test_a_start_at_the_very_beginning_is_no_guess(self):
        g = engine.Guard(devices())
        tick(g, Q + timedelta(seconds=10), 8.4, None)
        self.assertFalse(g.quarter_estimated)


if __name__ == "__main__":
    unittest.main()
