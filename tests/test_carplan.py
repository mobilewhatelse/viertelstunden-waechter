"""Tests for the planned car load read from a charge plan."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
from forecast import apply_car_plan, parse_plan_windows, risk_windows, splice

TZ = timezone(timedelta(hours=1))
T0 = datetime(2027, 1, 12, 20, 0, tzinfo=TZ)


def series(n=16, typical=0.5, high=1.0, count=4):
    return [{"t": T0 + timedelta(minutes=15 * i), "typical": typical, "high": high, "n": count} for i in range(n)]


def window(start_q, end_q, energy, peak):
    return {"start": T0 + timedelta(minutes=15 * start_q), "end": T0 + timedelta(minutes=15 * end_q),
            "avg_kw": energy / ((end_q - start_q) * 0.25), "peak_kw": peak}


class ParseTest(unittest.TestCase):
    def test_parses_windows(self):
        w = parse_plan_windows([{"start": "2027-01-12T22:00:00+01:00", "end": "2027-01-12T23:00:00+01:00", "energy_kwh": 8.0, "peak_kw": 11.0}], TZ)
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["avg_kw"], 8.0)
        self.assertEqual(w[0]["peak_kw"], 11.0)

    def test_broken_entries_are_skipped(self):
        w = parse_plan_windows([
            "x", {"start": "kaputt", "end": "y"}, {"start": "2027-01-12T22:00:00+01:00"},
            {"start": "2027-01-12T23:00:00+01:00", "end": "2027-01-12T22:00:00+01:00", "energy_kwh": 5},   # ends before it starts
            {"start": "2027-01-12T22:00:00+01:00", "end": "2027-01-12T23:00:00+01:00", "energy_kwh": 0, "peak_kw": 0},
            {"start": "2027-01-12T22:00:00", "end": "2027-01-12T22:30:00", "energy_kwh": 2.0, "peak_kw": 4.0},  # no zone: local
        ], TZ)
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["avg_kw"], 4.0)
        self.assertEqual(parse_plan_windows(None, TZ), [])


class ApplyTest(unittest.TestCase):
    def test_planned_load_is_added_inside_the_window_only(self):
        house, view = series(), series(typical=3.0, high=6.0)       # the view with the learned wallbox pattern is higher
        out = apply_car_plan(house, view, [window(4, 8, 8.0, 11.0)], T0 + timedelta(hours=4))   # 21:00-22:00, 8 kWh
        self.assertEqual(out[3]["high"], 1.0)                        # before the window: house only (not the learned pattern)
        self.assertEqual(out[4]["typical"], 8.5)                     # 0.5 + 8 kWh / 1 h
        self.assertEqual(out[4]["high"], 12.0)                       # 1.0 + 11 kW peak
        self.assertEqual(out[7]["high"], 12.0)
        self.assertEqual(out[8]["high"], 1.0)                        # after the window

    def test_after_departure_the_usual_view_stays(self):
        house, view = series(), series(typical=3.0, high=6.0)
        out = apply_car_plan(house, view, [], T0 + timedelta(hours=2))
        self.assertEqual(out[7]["high"], 1.0)                        # before departure: house only
        self.assertEqual(out[8]["high"], 6.0)                        # from departure: the view (learned wallbox pattern)
        self.assertEqual(len(out), 16)

    def test_no_windows_means_no_car_load_until_departure(self):
        out = apply_car_plan(series(), series(high=9.0), [], T0 + timedelta(hours=10))
        self.assertTrue(all(q["high"] == 1.0 for q in out))

    def test_unknown_house_data_stays_unknown(self):
        house = series()
        house[2] = {"t": house[2]["t"], "typical": None, "high": None, "n": 0}
        out = apply_car_plan(house, series(), [window(0, 16, 20.0, 5.0)], T0 + timedelta(hours=10))
        self.assertIsNone(out[2]["high"])
        self.assertEqual(out[1]["high"], 6.0)

    def test_two_cars_add_up(self):
        out = apply_car_plan(series(), series(), [window(4, 8, 4.0, 4.0), window(6, 10, 4.0, 4.0)], T0 + timedelta(hours=10))
        self.assertEqual(out[6]["high"], 1.0 + 4.0 + 4.0)

    def test_risk_windows_follow_the_plan(self):
        # the plan puts 11 kW in 21:00-22:00 on a quiet house: a risk window exactly there (target 9.5 kW)
        out = apply_car_plan(series(), series(), [window(4, 8, 11.0, 11.0)], T0 + timedelta(hours=10))
        w = risk_windows(out, 9.5)
        self.assertEqual(len(w), 1)
        self.assertEqual((w[0]["start"], w[0]["end"]), (T0 + timedelta(hours=1), T0 + timedelta(hours=2)))

    def test_plan_that_is_not_executed_never_lowers_the_forecast(self):
        # learn mode: the plan says "not needed", but the car may charge anyway -> the learned wallbox pattern stays
        house, view = series(), series(typical=3.0, high=9.0)
        out = apply_car_plan(house, view, [], T0 + timedelta(hours=10), executed=False)
        self.assertTrue(all(q["high"] == 9.0 and q["typical"] == 3.0 for q in out))

    def test_plan_that_is_not_executed_still_adds_its_windows(self):
        # the planned window is higher than the learned pattern: it counts; outside it the learned pattern counts
        house, view = series(), series(typical=3.0, high=6.0)
        out = apply_car_plan(house, view, [window(4, 8, 8.0, 11.0)], T0 + timedelta(hours=4), executed=False)
        self.assertEqual(out[3]["high"], 6.0)
        self.assertEqual(out[4]["high"], 12.0)
        self.assertEqual(out[4]["typical"], 8.5)
        self.assertEqual(out[8]["high"], 6.0)

    def test_not_executed_with_unknown_view_keeps_the_plan_value(self):
        house, view = series(), series()
        view[1] = {"t": view[1]["t"], "typical": None, "high": None, "n": 0}
        out = apply_car_plan(house, view, [], T0 + timedelta(hours=10), executed=False)
        self.assertEqual(out[1]["high"], 1.0)

    def test_without_a_plan_nothing_is_changed_here(self):
        # the function is only called with a plan; the original series are not modified
        house, view = series(), series(high=6.0)
        apply_car_plan(house, view, [window(0, 4, 4.0, 4.0)], T0 + timedelta(hours=4))
        self.assertEqual(house, series())
        self.assertEqual(view, series(high=6.0))


class SpliceTest(unittest.TestCase):
    def test_first_hour_house_then_the_learned_wallbox(self):
        out = splice(series(typical=0.5, high=1.0), series(typical=3.0, high=11.0), 4)
        self.assertEqual([q["high"] for q in out[:5]], [1.0, 1.0, 1.0, 1.0, 11.0])
        self.assertEqual(len(out), 16)


if __name__ == "__main__":
    unittest.main()
