"""Tests for the load forecast model."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
from forecast import MAX_SAMPLES, LoadModel, floor_quarter, hourly, risk_windows, slot_of

TZ = timezone(timedelta(hours=1))
SUNDAY = datetime(2027, 1, 10, 0, 0, tzinfo=TZ)  # a Sunday


def learn_weeks(model: LoadModel, weeks: int, spike=(17.5, 19.0), spike_kw=8.0, base_kw=0.5) -> None:
    for w in range(weeks):
        for d in range(7):
            for q in range(96):
                t = SUNDAY - timedelta(weeks=weeks - w) + timedelta(days=d, minutes=15 * q)
                hour = q / 4
                is_sun = t.weekday() == 6
                model.add(t, spike_kw if is_sun and spike[0] <= hour < spike[1] else base_kw)


class ModelTests(unittest.TestCase):
    def test_slot_and_floor(self):
        self.assertEqual(slot_of(SUNDAY), 6 * 96)
        self.assertEqual(slot_of(SUNDAY.replace(hour=17, minute=44)), 6 * 96 + 70)
        self.assertEqual(floor_quarter(SUNDAY.replace(hour=17, minute=44, second=9)), SUNDAY.replace(hour=17, minute=30))

    def test_learns_the_sunday_evening_peak(self):
        m = LoadModel()
        learn_weeks(m, 4)
        typical, high, n = m.predict(SUNDAY.replace(hour=18, minute=0))
        self.assertEqual((typical, high, n), (8.0, 8.0, 4))
        self.assertEqual(m.predict(SUNDAY.replace(hour=18) + timedelta(days=1))[1], 0.5)  # Monday

    def test_unknown_slot_has_no_prediction(self):
        self.assertIsNone(LoadModel().predict(SUNDAY))

    def test_keeps_only_the_latest_samples(self):
        m = LoadModel()
        for i in range(20):
            m.add(SUNDAY, float(i))
        self.assertEqual(len(m.slots[slot_of(SUNDAY)]), MAX_SAMPLES)
        self.assertEqual(m.slots[slot_of(SUNDAY)][-1], 19.0)

    def test_single_outlier_is_ignored_with_enough_samples(self):
        m = LoadModel()
        for kw in (1.0, 1.1, 0.9, 1.0, 14.0):  # one odd evening
            m.add(SUNDAY, kw)
        self.assertEqual(m.predict(SUNDAY)[1], 1.1)

    def test_counter_jumps_are_not_learned(self):
        m = LoadModel()
        m.add(SUNDAY, 120.0)
        m.add(SUNDAY, -3.0)
        self.assertEqual(m.samples, 0)

    def test_hourly_bootstrap_fills_four_quarters(self):
        m = LoadModel()
        m.add_hourly(SUNDAY.replace(hour=18), 3.2)
        self.assertEqual([m.predict(SUNDAY.replace(hour=18, minute=x))[0] for x in (0, 15, 30, 45)], [3.2] * 4)

    def test_roundtrip(self):
        m = LoadModel()
        learn_weeks(m, 2)
        m2 = LoadModel.from_dict(m.to_dict())
        self.assertEqual(m2.slots, m.slots)
        self.assertEqual(LoadModel.from_dict({"slots": {"x": [1], "5": ["a"]}}).samples, 0)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.model = LoadModel()
        learn_weeks(self.model, 4)

    def test_risk_window_on_sunday_evening(self):
        series = self.model.horizon(SUNDAY.replace(hour=12), 24)
        windows = risk_windows(series, target_kw=7.0)
        self.assertEqual(len(windows), 1)
        w = windows[0]
        self.assertEqual((w["start"].hour, w["start"].minute, w["end"].hour, w["end"].minute), (17, 30, 19, 0))
        self.assertEqual(w["high_kw"], 8.0)

    def test_no_window_when_target_is_above_the_peak(self):
        self.assertEqual(risk_windows(self.model.horizon(SUNDAY.replace(hour=12), 24), 9.5), [])

    def test_one_sample_is_not_enough_for_a_warning(self):
        m = LoadModel()
        m.add(SUNDAY.replace(hour=18), 12.0)
        self.assertEqual(risk_windows(m.horizon(SUNDAY.replace(hour=17), 3), 9.5), [])

    def test_hourly_condensing(self):
        h = hourly(self.model.horizon(SUNDAY.replace(hour=12), 24))
        self.assertEqual(len(h), 24)
        evening = next(x for x in h if x["t"].hour == 18)
        self.assertEqual(evening["high"], 8.0)


if __name__ == "__main__":
    unittest.main()
