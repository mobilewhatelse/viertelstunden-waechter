"""Tests for the weather correction of the load forecast."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
from forecast import FIT_MIN_DAYS, LoadModel, WeatherCurve, combine, fit_curve

TZ = timezone(timedelta(hours=1))
MON = datetime(2027, 1, 11, 18, 0, tzinfo=TZ)  # a Monday, 18:00


def days_from(temps, base=1.0, heat=0.0, cool=0.0):
    out = []
    for i, t in enumerate(temps):
        kw = base + heat * max(0.0, 15 - t) + cool * max(0.0, t - 22)
        out.append((i % 7, kw, t))
    return out


class FitTest(unittest.TestCase):
    def test_recovers_heating_slope(self):
        temps = [-5 + (i * 7) % 20 for i in range(60)]  # -5 .. 14 degrees, no hot days
        curve, info = fit_curve(days_from(temps, heat=0.05))
        self.assertAlmostEqual(curve.heat_kw_per_k, 0.05, places=2)
        self.assertEqual(curve.cool_kw_per_k, 0.0)  # no hot day: no cooling slope invented
        self.assertGreater(info["r2"], 0.9)

    def test_recovers_cooling_slope_in_summer(self):
        temps = [18 + (i * 5) % 16 for i in range(60)]  # 18 .. 33 degrees
        curve, _ = fit_curve(days_from(temps, cool=0.12))
        self.assertAlmostEqual(curve.cool_kw_per_k, 0.12, places=2)
        self.assertEqual(curve.heat_kw_per_k, 0.0)

    def test_both_slopes(self):
        temps = [-5 + (i * 11) % 40 for i in range(120)]
        curve, _ = fit_curve(days_from(temps, heat=0.04, cool=0.1))
        self.assertAlmostEqual(curve.heat_kw_per_k, 0.04, places=2)
        self.assertAlmostEqual(curve.cool_kw_per_k, 0.1, places=2)

    def test_too_few_days_no_correction(self):
        curve, info = fit_curve(days_from([0.0] * (FIT_MIN_DAYS - 1), heat=0.05))
        self.assertFalse(curve.active)
        self.assertEqual(info["days"], FIT_MIN_DAYS - 1)

    def test_mild_weather_no_correction(self):
        curve, _ = fit_curve(days_from([16 + (i % 5) for i in range(40)], heat=0.05))
        self.assertFalse(curve.active)

    def test_never_negative(self):
        # load falls when it gets colder: nonsense for the model, so no negative slope
        days = [(i % 7, 2.0 + 0.1 * (i % 15), 0.0 + (i % 15) * -1.0) for i in range(40)]
        curve, _ = fit_curve(days)
        self.assertGreaterEqual(curve.heat_kw_per_k, 0.0)


class PredictTest(unittest.TestCase):
    def model(self, temps_each):
        m = LoadModel()
        for w, t in enumerate(temps_each):
            m.add(MON - timedelta(weeks=len(temps_each) - w), 1.0 + 0.05 * max(0.0, 15 - t), t)
        return m

    def test_cold_day_raises_forecast(self):
        m = self.model([10, 12, 8, 14])
        curve = WeatherCurve(0.05, 0.0)
        mild = m.predict(MON, 14.0, curve)
        cold = m.predict(MON, -5.0, curve)
        self.assertGreater(cold[0], mild[0] + 0.8)       # 19 K colder: about +1 kW
        self.assertAlmostEqual(cold[0], 1.0 + 0.05 * 20, places=1)

    def test_without_curve_or_temperature_nothing_changes(self):
        m = self.model([10, 12, 8, 14])
        base = m.predict(MON)
        self.assertEqual(m.predict(MON, -5.0, None), base)
        self.assertEqual(m.predict(MON, None, WeatherCurve(0.05, 0.0)), base)
        self.assertEqual(m.predict(MON, -5.0, WeatherCurve(0.0, 0.0)), base)

    def test_samples_without_temperature_stay(self):
        m = LoadModel()
        for w in range(4):
            m.add(MON - timedelta(weeks=4 - w), 1.0)
        self.assertEqual(m.predict(MON, -5.0, WeatherCurve(0.05, 0.0))[0], 1.0)

    def test_hot_day_with_air_conditioning(self):
        m = LoadModel()
        for w in range(4):
            m.add(MON - timedelta(weeks=4 - w), 0.6, 20.0)
        hot = m.predict(MON, 34.0, WeatherCurve(0.0, 0.1))
        self.assertAlmostEqual(hot[0], 0.6 + 0.1 * 12, places=2)

    def test_never_below_zero(self):
        m = LoadModel()
        for w in range(4):
            m.add(MON - timedelta(weeks=4 - w), 0.3, -10.0)
        self.assertGreaterEqual(m.predict(MON, 20.0, WeatherCurve(0.2, 0.0))[0], 0.0)

    def test_horizon_uses_temperature_function(self):
        m = self.model([10, 12, 8, 14])
        series = m.horizon(MON, 1, lambda t: -5.0, WeatherCurve(0.05, 0.0))
        self.assertGreater(series[0]["typical"], 1.5)  # only the 18:00 quarter has samples


class StoreTest(unittest.TestCase):
    def test_roundtrip_keeps_temperatures(self):
        m = LoadModel()
        m.add(MON, 1.0, 3.5)
        m.add(MON, 1.2)
        back = LoadModel.from_dict(m.to_dict())
        self.assertEqual(back.slots, m.slots)
        self.assertEqual(back.temps, m.temps)

    def test_old_store_without_temperatures(self):
        back = LoadModel.from_dict({"slots": {"10": [1.0, 2.0, 3.0]}})
        self.assertEqual(back.temps[10], [None, None, None])
        self.assertEqual(back.predict(datetime(2027, 1, 11, 2, 30, tzinfo=TZ), -5.0, WeatherCurve(0.05, 0.0))[2], 3)

    def test_trim_keeps_lists_aligned(self):
        m = LoadModel()
        for i in range(12):
            m.add(MON, float(i), float(i))
        k = next(iter(m.slots))
        self.assertEqual(len(m.slots[k]), len(m.temps[k]))
        self.assertEqual(m.temps[k][-1], 11.0)

    def test_combine_keeps_house_temperatures(self):
        house, wb = LoadModel(), LoadModel()
        for w in range(4):
            t = MON - timedelta(weeks=4 - w)
            house.add(t, 1.0, 10.0)
            wb.add(t, 2.0)
        both = combine(house, wb)
        cold = both.predict(MON, -5.0, WeatherCurve(0.05, 0.0))
        self.assertAlmostEqual(cold[0], 3.0 + 0.05 * 15, places=2)  # wallbox part untouched, house part corrected


if __name__ == "__main__":
    unittest.main()
