"""0.16.0: the 'kW too much' of a log line / the choice of devices is never larger than the power that actually flows.
Seen in the setup film (2026-11-27): shortly before the end of a quarter hour that is already over its budget, the allowed
power (budget / remaining time) goes strongly negative and the line said '245.9 kW zu viel'. Same arithmetic in 0.15.1."""

from __future__ import annotations

import re
import unittest
from dataclasses import replace
from datetime import timedelta

from sim import House, START, devices, engine


def _guard(observe=False):
    devs = [replace(d, observe_only=True) if observe else d for d in devices()]
    return engine.Guard(devs)


def _excess_values(log):
    return [float(m) for ln in log for m in re.findall(r"([\d.]+) kW zu viel", ln)]


class ExcessIsCappedTests(unittest.TestCase):
    def _late_over_budget(self, observe):
        """A 40 kW load from minute 10 pushes the quarter far over its budget; the last minutes are checked every second."""
        guard, house, log = _guard(observe), House(cooker=[(10, 15, 40.0)], base_kw=0.4), []
        t, self.peak = 0.0, 0.0
        while t < 15 * 60:
            now = START + timedelta(seconds=t)
            grid = house.advance(t / 60.0)
            self.peak = max(self.peak, grid)
            acts = guard.step(now, grid, house.counter_kwh, house.readings(), 10.0, 0.5, True)
            for a in acts:
                house.apply(a, t / 60.0)
                if a.text:
                    log.append(a.text)
            t += 1.0 if t >= 10 * 60 else 20.0
        return log, guard

    def test_observe_note_never_exceeds_the_flowing_power(self):
        log, _ = self._late_over_budget(True)
        vals = _excess_values(log)
        self.assertTrue(vals, log)
        self.assertLessEqual(max(vals), self.peak + 0.1, log)

    def test_real_intervention_text_never_exceeds_the_flowing_power(self):
        log, _ = self._late_over_budget(False)
        vals = _excess_values(log)
        self.assertTrue(vals, log)
        self.assertLessEqual(max(vals), self.peak + 0.1, log)


if __name__ == "__main__":
    unittest.main()
