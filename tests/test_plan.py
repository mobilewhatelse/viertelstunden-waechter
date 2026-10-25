"""Tests for the charge plan."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
from plan import charging_allowed, make_plan, needed_kwh

TZ = timezone(timedelta(hours=1))
NOW = datetime(2027, 1, 12, 17, 5, tzinfo=TZ)
DEPART = datetime(2027, 1, 13, 7, 0, tzinfo=TZ)


def load(high_by_hour=None, default=0.5):
    """Quarter hours from 17:00 to 08:00 with an expected import per hour."""
    out = []
    t = NOW.replace(minute=0)
    while t < DEPART + timedelta(hours=1):
        high = (high_by_hour or {}).get(t.hour, default)
        out.append({"t": t, "typical": high / 2, "high": high, "n": 4})
        t += timedelta(minutes=15)
    return out


class NeedTests(unittest.TestCase):
    def test_needed_energy(self):
        self.assertAlmostEqual(needed_kwh(40, 80, 60, 0.9), 26.67, places=1)
        self.assertEqual(needed_kwh(90, 80, 60), 0.0)


class PlanTests(unittest.TestCase):
    def plan(self, **kw):
        args = dict(now=NOW, departure=DEPART, soc=40, target_soc=80, capacity_kwh=60, max_kw=11.0, min_kw=1.4,
                    target_kw=9.5, load=load())
        args.update(kw)
        return make_plan(**args)

    def test_charges_in_the_quietest_hours_and_is_ready_in_time(self):
        busy = {h: 6.0 for h in (17, 18, 19, 20, 21)}  # evening with cooking
        p = self.plan(load=load(busy))
        self.assertEqual(p["status"], "planned")
        self.assertAlmostEqual(p["planned_kwh"], p["needed_kwh"], delta=1.5)
        self.assertLessEqual(p["ready_at"], DEPART)
        # nothing is planned in the busy evening hours while the quiet night can take it
        self.assertTrue(all(w["start"].hour not in (17, 18, 19, 20) for w in p["windows"]), p["windows"])

    def test_never_exceeds_the_peak_target(self):
        busy = {h: 6.0 for h in range(17, 24)}  # 3.5 kW of room all evening
        p = self.plan(load=load(busy), soc=70, target_soc=80)
        for t, kw in p["quarters"].items():
            hi = next(q["high"] for q in load(busy) if q["t"] == t)
            self.assertLessEqual(hi + kw, 9.5 + 1e-6, (t, kw, hi))

    def test_infeasible_says_how_much_is_missing(self):
        p = self.plan(load=load(default=9.0), soc=10, target_soc=100)  # 0.5 kW room only: below the wallbox minimum
        self.assertEqual(p["status"], "infeasible")
        self.assertGreater(p["shortfall_kwh"], 10)

    def test_solar_quarters_come_first(self):
        tomorrow_sun = {NOW.replace(day=13, hour=h, minute=m): 8.0 for h in range(10, 14) for m in (0, 15, 30, 45)}
        dep = datetime(2027, 1, 13, 15, 0, tzinfo=TZ)
        ld = []
        t = NOW.replace(minute=0)
        while t < dep + timedelta(hours=1):
            ld.append({"t": t, "typical": 0.3, "high": 0.5, "n": 4})
            t += timedelta(minutes=15)
        p = make_plan(NOW, dep, 40, 80, 60, 11.0, 1.4, 9.5, ld, solar_kw=tomorrow_sun, base_kw=0.5)
        self.assertTrue(p["solar_used"])
        self.assertGreater(p["solar_kwh"], 0.5 * p["planned_kwh"], p)
        self.assertTrue(all(10 <= w["start"].hour < 14 for w in p["windows"] if w["solar_kwh"] > 0))

    def test_without_solar_forecast_it_still_plans(self):
        p = self.plan(solar_kw=None)
        self.assertFalse(p["solar_used"])
        self.assertEqual(p["status"], "planned")

    def test_not_needed_and_no_departure(self):
        self.assertEqual(self.plan(soc=85)["status"], "not_needed")
        self.assertEqual(self.plan(departure=NOW - timedelta(minutes=1))["status"], "no_departure")

    def test_latest_start(self):
        p = self.plan()
        self.assertAlmostEqual((DEPART - p["latest_start"]).total_seconds() / 3600, p["needed_kwh"] / 11.0, places=3)

    def test_charging_allowed_follows_the_quarters(self):
        p = self.plan(load=load({h: 6.0 for h in range(17, 24)}))
        first = min(p["quarters"])
        self.assertTrue(charging_allowed(p, first + timedelta(minutes=3)))
        self.assertFalse(charging_allowed(p, NOW))  # evening: planned pause
        self.assertIsNone(charging_allowed(self.plan(soc=85), NOW))  # not needed: the plan does not decide
        self.assertIsNone(charging_allowed(self.plan(load=load(default=9.0), soc=10, target_soc=100), NOW))

    def test_current_quarter_counts_only_its_rest(self):
        p = make_plan(NOW, NOW + timedelta(minutes=30), 79, 80, 60, 11.0, 1.4, 9.5, load())
        self.assertLessEqual(p["planned_kwh"], 11.0 * 0.5 + 0.01)


if __name__ == "__main__":
    unittest.main()
