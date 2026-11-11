"""Tests for the planned car load read from a charge plan."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
from forecast import (add_running_charge, apply_car_plan, parse_plan_windows, quiet_until, risk_windows, running_charge_hours, splice,
                      wallbox_total_w)

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


class RunningChargeTest(unittest.TestCase):
    """Seen on 2026-11-10: the car charged with 8.6 kW in the evening, the forecast showed 0.4 to 0.8 kW (evenings were rarely
    charging time in the learned pattern)."""
    T0 = datetime(2026, 11, 10, 19, 0, tzinfo=timezone(timedelta(hours=1)))

    def series(self, typical, high, n=16):
        return [{"t": self.T0 + timedelta(minutes=15 * i), "typical": typical, "high": high} for i in range(n)]

    def test_hours_from_what_is_missing(self):
        self.assertAlmostEqual(running_charge_hours(8.6, 62, 100, 66, 90), (0.38 * 66 / 0.9) / 8.6, places=3)
        self.assertEqual(running_charge_hours(8.6, None, None, None), 2.0)          # end unknown: a usual duration
        self.assertEqual(running_charge_hours(8.6, 100, 100, 66), 0.0)              # full
        self.assertEqual(running_charge_hours(1.0, 0, 100, 100), 12.0)              # capped
        self.assertEqual(running_charge_hours(0.0, 50, 100, 66), 0.0)

    def test_the_forecast_has_the_charge_until_its_end_and_is_never_lowered(self):
        house, view = self.series(0.3, 0.6), self.series(0.3, 0.8)
        view[10]["high"] = 11.0                                                     # a learned peak later that evening stays
        out = add_running_charge(house, view, 8.6, self.T0 + timedelta(hours=2))
        self.assertEqual([q["high"] for q in out[:8]], [9.2] * 8)
        self.assertEqual(out[0]["typical"], 8.9)
        self.assertEqual(out[8]["high"], 0.8)                                       # after the end: as before
        self.assertEqual(out[10]["high"], 11.0)

    def test_one_wallbox_entered_twice_counts_once(self):
        self.assertEqual(wallbox_total_w([(8500.0, False), (8570.0, True)]), 8500.0)   # directly and as evcc loadpoint (observe only)
        self.assertEqual(wallbox_total_w([(8500.0, False), (3600.0, True)]), 12100.0)  # a second wallbox that is only observed
        self.assertEqual(wallbox_total_w([(None, False), (7000.0, True)]), 7000.0)
        self.assertEqual(wallbox_total_w([(8500.0, False), (8500.0, False)]), 17000.0) # two real wallboxes


class QuietUntilTest(unittest.TestCase):
    TZ = timezone(timedelta(hours=1))
    NOW = datetime(2026, 11, 10, 19, 0, tzinfo=TZ)
    DEP = datetime(2026, 11, 11, 7, 0, tzinfo=TZ)

    def test_an_executed_plan_covers_the_car_until_the_next_need(self):
        h = {"status": "ok", "first_need": {"window_start": "2026-11-12T17:30:00+01:00"}}
        self.assertEqual(quiet_until(h, self.DEP, self.NOW, self.TZ), datetime(2026, 11, 12, 17, 30, tzinfo=self.TZ))

    def test_no_need_at_all_covers_the_whole_day(self):
        self.assertEqual(quiet_until({"status": "ok", "first_need": None}, self.DEP, self.NOW, self.TZ), self.NOW + timedelta(hours=24))

    def test_without_a_look_ahead_it_is_the_departure(self):
        self.assertEqual(quiet_until(None, self.DEP, self.NOW, self.TZ), self.DEP)
        self.assertEqual(quiet_until({"status": "unknown_soc"}, self.DEP, self.NOW, self.TZ), self.DEP)
        self.assertEqual(quiet_until({"status": "ok", "first_need": {"window_start": "kaputt"}}, self.DEP, self.NOW, self.TZ), self.DEP)


if __name__ == "__main__":
    unittest.main()
