"""Display option *smooth the forecast at the quarter start* (0.15.1, feedback 19.11.2026: "the forecast shows 10.96" right
after a quarter hour began). Only what the sensor shows changes; the control, the early warning and the forecast log keep the
projection of the guard."""

from __future__ import annotations

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import sim  # noqa: F401  (puts the integration folder on sys.path)
import engine
from sim import devices

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
TZ = timezone(timedelta(hours=1))


def _method(name: str):
    tree = ast.parse((PKG / "coordinator.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Waechter")
    return next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def _forecast_shown():
    """The method of the coordinator as a plain function (the coordinator itself needs Home Assistant)."""
    node = _method("forecast_shown")
    node.returns = None
    node.args.args[0].annotation = None
    ns = {"smoothed_forecast": engine.smoothed_forecast}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "coordinator.py", "exec"), ns)  # noqa: S102
    return ns["forecast_shown"]


class SmoothedForecastTest(unittest.TestCase):
    def test_weight_moves_from_the_typical_value_to_the_measurement(self):
        self.assertEqual(engine.smoothed_forecast(10.96, 2.0, 0), 2.0)
        self.assertAlmostEqual(engine.smoothed_forecast(10.96, 2.0, 60), 6.48, places=2)
        self.assertEqual(engine.smoothed_forecast(10.96, 2.0, 120), 10.96)
        self.assertEqual(engine.smoothed_forecast(10.96, 2.0, 400), 10.96)

    def test_without_a_typical_value_the_projection_stays(self):
        self.assertEqual(engine.smoothed_forecast(10.96, None, 10), 10.96)
        self.assertIsNone(engine.smoothed_forecast(None, 2.0, 10))

    def test_the_guard_keeps_its_projection(self):
        # a kettle of 11 kW right after the quarter start: the guard works with the projection as before
        g = engine.Guard(devices())
        q = datetime(2026, 11, 19, 18, 0, tzinfo=TZ)
        g.step(q + timedelta(seconds=10), 1.0, None, {}, 10.0, 0.5, True)
        g.step(q + timedelta(seconds=30), 11.0, None, {}, 10.0, 0.5, True)
        raw = g.values["forecast_kw"]
        self.assertGreater(raw, 5.0)
        self.assertNotIn("forecast_shown_kw", g.values)


class CoordinatorTest(unittest.TestCase):
    def _w(self, smooth: bool, at_s: float, typical_t_is_q: bool = True):
        q = datetime(2026, 11, 19, 18, 0, tzinfo=TZ)
        guard = SimpleNamespace(values={"forecast_kw": 10.96, "quarter": q}, _now=q + timedelta(seconds=at_s))
        f = {"now": {"t": q if typical_t_is_q else q - timedelta(minutes=15), "typical": 2.0}}
        return SimpleNamespace(guard=guard, forecast=f, forecast_smooth=smooth)

    def test_off_by_default_shows_the_projection(self):
        self.assertEqual(_forecast_shown()(self._w(False, 10)), 10.96)

    def test_on_smooths_only_the_first_two_minutes(self):
        fn = _forecast_shown()
        self.assertLess(fn(self._w(True, 10)), 3.0)
        self.assertEqual(fn(self._w(True, 150)), 10.96)

    def test_a_load_forecast_of_another_quarter_hour_is_not_used(self):
        self.assertEqual(_forecast_shown()(self._w(True, 10, typical_t_is_q=False)), 10.96)

    def test_control_warning_and_log_do_not_use_the_shown_value(self):
        for name in ("_prewarning", "_protokoll_step", "_tick"):
            try:
                text = ast.unparse(_method(name))
            except StopIteration:
                continue
            self.assertNotIn("forecast_shown", text, name)
            self.assertNotIn("forecast_smooth", text, name)
        self.assertNotIn("forecast_smooth", (PKG / "engine.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
