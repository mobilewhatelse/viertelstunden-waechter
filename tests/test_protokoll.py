"""Local log (0.15.1, protokoll.py): forecast against result per quarter hour and the starts of devices.

Stays in Home Assistant: never in the bug report or the diagnostics (only the number of days), no network. coordinator.py imports
Home Assistant, so its use of the log is read from the source (ast), like test_datenkatalog.py."""

from __future__ import annotations

import ast
import json
import random
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
# asyncio must be loaded without the integration folder on the path (it has its own select.py)
_path = list(sys.path)
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != PKG]
import asyncio  # noqa: E402,F401
sys.path[:] = _path
sys.path.insert(0, str(PKG))

import fehlerbericht as fb  # noqa: E402
import protokoll as pr  # noqa: E402

TZ = timezone(timedelta(hours=1))
Q = datetime(2026, 12, 1, 18, 0, tzinfo=TZ)


def _ticks(p: pr.Protokoll, q: datetime, values: dict[int, float], step_s: int = 20, until_s: int = 900, **kw) -> None:
    """One cycle every `step_s` seconds; `values` maps a second to the projection from then on."""
    cur = None
    for s in range(0, until_s, step_s):
        cur = values.get(s, cur)
        p.quarter_tick(q + timedelta(seconds=s), q, cur, **kw)


def _ha_json(data) -> bytes:
    """What Home Assistant's Store writes: the data wrapped, indented by 2."""
    return json.dumps({"version": 1, "minor_version": 1, "key": "viertelstunden_waechter.x.protokoll", "data": data},
                      indent=2, ensure_ascii=False).encode()


class ForecastLogTests(unittest.TestCase):
    def test_marks_typical_high_and_end(self):
        p = pr.Protokoll()
        _ticks(p, Q, {0: 2.0, 60: 3.456, 120: 5.0, 180: 8.59, 300: 8.6, 600: 8.72, 700: 9.9},
               typ=1.2, hoch=4.0, haus_typ=0.3, haus_hoch=0.9)
        self.assertTrue(p.quarter_end(Q, 8.75))
        [r] = p.rows("2026-12-01")
        self.assertEqual(r["zeit"], "18:00")
        self.assertEqual((r["m1"], r["m3"], r["m5"], r["m10"]), (3.46, 8.59, 8.6, 8.72))   # 0.01 kW
        self.assertEqual((r["typ"], r["hoch"], r["haus_typ"], r["haus_hoch"], r["ende"]), (1.2, 4.0, 0.3, 0.9, 8.75))
        self.assertEqual(r["flags"], 0)
        self.assertEqual(p.open, {})

    def test_typical_taken_once_when_it_comes_late(self):
        """The forecast is worked out every 5 minutes: typical/high may come in the middle; the first value stays."""
        p = pr.Protokoll()
        p.quarter_tick(Q + timedelta(seconds=20), Q, 1.0)
        self.assertTrue(p.needs_forecast(Q))
        p.quarter_tick(Q + timedelta(seconds=200), Q, 1.0, typ=2.0, hoch=3.0, haus_typ=1.0, haus_hoch=1.5)
        self.assertFalse(p.needs_forecast(Q))
        p.quarter_tick(Q + timedelta(seconds=500), Q, 1.0, typ=9.0, hoch=9.0, haus_typ=9.0, haus_hoch=9.0)
        p.quarter_end(Q, 1.0)
        r = p.rows("2026-12-01")[0]
        self.assertEqual((r["typ"], r["hoch"], r["haus_typ"]), (2.0, 3.0, 1.0))

    def test_gap_leaves_the_missed_marks_empty(self):
        """No cycle between minute 2 and 7 (Home Assistant busy): minute 3 and 5 are not filled with a later value."""
        p = pr.Protokoll()
        for s in (0, 20, 60, 80, 100) + tuple(range(420, 900, 20)):
            p.quarter_tick(Q + timedelta(seconds=s), Q, 4.0 + s / 1000)
        p.quarter_end(Q, 4.5)
        r = p.rows("2026-12-01")[0]
        self.assertEqual(r["m1"], 4.06)
        self.assertIsNone(r["m3"])
        self.assertIsNone(r["m5"])
        self.assertEqual(r["m10"], 4.6)

    def test_flags_intervention_and_estimate(self):
        p = pr.Protokoll()
        _ticks(p, Q, {0: 9.0}, eingriff=True)
        p.quarter_end(Q, 9.5)
        q2 = Q + timedelta(minutes=15)
        _ticks(p, q2, {0: 3.0}, geschaetzt=True)
        p.quarter_end(q2, 3.0)
        q3 = q2 + timedelta(minutes=15)
        _ticks(p, q3, {0: 3.0})
        p.quarter_end(q3, 3.0, geschaetzt=True)   # a counter gap found only at the end
        flags = [r["flags"] for r in p.rows("2026-12-01")]
        self.assertEqual(flags, [pr.F_EINGRIFF, pr.F_GESCHAETZT, pr.F_GESCHAETZT])

    def test_restart_within_the_quarter_hour_continues_its_row(self):
        p = pr.Protokoll()
        _ticks(p, Q, {0: 2.0, 60: 2.5, 180: 3.5}, until_s=240, typ=1.0, hoch=2.0)
        p2 = pr.Protokoll.from_store(json.loads(json.dumps(p.archive_data())), json.loads(json.dumps(p.recent_data())))
        for s in range(400, 900, 20):
            p2.quarter_tick(Q + timedelta(seconds=s), Q, 4.0)
        p2.quarter_end(Q, 4.1)
        [r] = p2.rows("2026-12-01")
        self.assertEqual((r["m1"], r["m3"], r["m5"], r["m10"], r["ende"]), (2.5, 3.5, None, 4.0, 4.1))
        self.assertEqual(r["typ"], 1.0)

    def test_quarter_hour_without_end_is_closed_later(self):
        """Home Assistant was away at the end of the quarter hour: the row is written without end value after 30 minutes."""
        p = pr.Protokoll()
        _ticks(p, Q, {0: 2.0}, until_s=400)
        self.assertFalse(p.close_stale(Q + timedelta(minutes=20)))
        self.assertTrue(p.close_stale(Q + timedelta(minutes=31)))
        [r] = p.rows("2026-12-01")
        self.assertEqual(r["m1"], 2.0)
        self.assertIsNone(r["ende"])
        self.assertFalse(p.quarter_end(Q, 2.0))          # written once only
        self.assertEqual(len(p.rows("2026-12-01")), 1)

    def test_end_without_any_tick_and_empty_rows_left_out(self):
        """The first cycle after a start may bring the end of a quarter hour it has not seen: the end value alone is kept.
        A quarter hour that has nothing at all is not written."""
        p = pr.Protokoll()
        self.assertTrue(p.quarter_end(Q, 1.5))
        p.open[(Q + timedelta(minutes=15)).isoformat()] = [None] * len(pr.Q_FIELDS)
        p.close_stale(Q + timedelta(hours=2))
        [r] = p.rows("2026-12-01")
        self.assertEqual((r["m1"], r["ende"]), (None, 1.5))
        self.assertEqual(p.open, {})

    def test_row_goes_to_the_day_of_its_start(self):
        """The quarter hour 23:45 ends at midnight: it belongs to the day it began."""
        p = pr.Protokoll()
        q = datetime(2026, 12, 1, 23, 45, tzinfo=TZ)
        _ticks(p, q, {0: 1.0})
        p.quarter_end(q, 1.0)
        self.assertEqual([r["zeit"] for r in p.rows("2026-12-01")], ["23:45"])
        self.assertEqual(p.rows("2026-12-02"), [])

    def test_garbage_in_the_store_is_left_out(self):
        p = pr.Protokoll.from_store({"days": {"2026-12-01": {"q": "72,100;x;73,,,,,,,,,50"}, "kaputt": 5, "2026-12-02": "x"},
                                     "devs": "nope"}, {"open": {"a": [1, 2]}, "days": []})
        self.assertEqual(p.days_count(), 1)
        self.assertEqual([r["slot"] for r in p.rows("2026-12-01")], [72, 73])
        self.assertEqual(p.rows("2026-12-01")[1]["ende"], 0.5)
        self.assertEqual(p.open, {})
        self.assertEqual(pr.Protokoll.from_store(None, None).days_count(), 0)
        self.assertEqual(pr.Protokoll.from_store("x", 5).days_count(), 0)


class KeepAndSizeTests(unittest.TestCase):
    @staticmethod
    def _fill(days: int, value, runs_per_day: int = 0) -> pr.Protokoll:
        p = pr.Protokoll()
        start = datetime(2025, 10, 1, tzinfo=TZ)
        for i in range(days * 96):
            q = start + timedelta(minutes=15 * i)
            p.open[q.isoformat()] = [pr._c(value()) for _ in range(9)] + [3]
            p.quarter_end(q, value())
        for d in range(days):
            for k in range(runs_per_day):
                t = start + timedelta(days=d, minutes=k * (1440 // max(1, runs_per_day)))
                p.add_run(f"01JDEVICE{k % 4:017d}", {"start": t, "spitze_w": 9876, "dauer_w": 9654, "stabil_s": 245,
                                                     "vorgabe_s": 123, "abstand_s": 20, "flags": 7})
        return p

    def test_400_days_are_kept_and_older_ones_dropped(self):
        p = self._fill(402, lambda: 1.0)
        self.assertEqual(p.days_count(), pr.KEEP_DAYS)
        self.assertNotIn("2025-10-01", p.days)
        self.assertNotIn("2025-10-02", p.days)
        self.assertIn("2025-10-03", p.days)
        self.assertEqual(len(p.rows("2025-10-03")), 96)

    def test_400_days_stay_below_2_mb(self):
        """Measured before building (catalogue 3.1): 38 400 quarter-hour rows with every field filled with three digits
        (up to 9.99 kW) and 12 starts a day, written as Home Assistant does (indented JSON): below 2 MB. The small store,
        written every 15 minutes, stays a few kilobytes."""
        rnd = random.Random(5)
        p = self._fill(400, lambda: rnd.uniform(1.0, 9.99), runs_per_day=12)
        self.assertEqual(sum(len(p.rows(d)) for d in p.days), 38_400)
        big, small = len(_ha_json(p.archive_data())), len(_ha_json(p.recent_data()))
        self.assertLess(big, 2_000_000, big)
        self.assertLess(small, 30_000, small)
        # a usual house (mostly below 1 kW) needs clearly less
        rnd = random.Random(6)
        usual = self._fill(400, lambda: rnd.choice([0.15, 0.3, 0.45, 0.8, 1.2, 3.4, 8.75]), runs_per_day=6)
        self.assertLess(len(_ha_json(usual.archive_data())), 1_600_000)

    def test_stores_round_trip_and_the_small_one_wins(self):
        p = self._fill(10, lambda: 2.0, runs_per_day=2)
        archive = json.loads(json.dumps(p.archive_data()))
        q = datetime(2025, 10, 10, 12, 0, tzinfo=TZ)   # one more quarter hour after the big store was written
        p.quarter_end(q, 7.0)
        recent = json.loads(json.dumps(p.recent_data()))
        self.assertEqual(len(recent["days"]), pr.RECENT_DAYS)
        p2 = pr.Protokoll.from_store(archive, recent)
        self.assertEqual(p2.days, p.days)
        self.assertEqual(p2.devs, p.devs)
        self.assertEqual(p2.runs("2025-10-05"), p.runs("2025-10-05"))

    def test_big_store_only_when_an_older_day_changed(self):
        p = pr.Protokoll()
        _ticks(p, Q, {0: 1.0})
        p.quarter_end(Q, 1.0)
        self.assertFalse(p.archive_due())          # only today changed: the small store is enough
        q = Q + timedelta(days=1)
        p.quarter_end(q, 1.0)
        self.assertTrue(p.archive_due())           # a new day: yesterday goes into the big store
        p.archive_data()
        self.assertFalse(p.archive_due())


class AnlaufTests(unittest.TestCase):
    """Example courses of a start, one value per cycle of 20 s."""

    @staticmethod
    def _run(a: pr.Anlauf, kind: str, course: list, t0: datetime = Q, **kw) -> list[dict]:
        out = []
        for i, item in enumerate(course):
            w, extra = (item, {}) if not isinstance(item, tuple) else (item[0], item[1])
            r = a.sample("dev", kind, t0 + timedelta(seconds=20 * i), w, **{**kw, **extra})
            if r is not None:
                out.append(r)
        return out

    def test_pump_with_inrush(self):
        """Off, then 1800 W for 40 s, 1100 W, then 900 W steady: peak 1800, steady 900, steady after 60 s."""
        a = pr.Anlauf()
        course = [0, 0, 0, 0, 1800, 1800, 1100] + [900] * 40 + [0, 0]
        [r] = self._run(a, "switch", course)
        self.assertEqual(r["start"], Q + timedelta(seconds=80))
        self.assertEqual((r["spitze_w"], r["dauer_w"]), (1800, 900))
        self.assertEqual(r["stabil_s"], 60)
        self.assertIsNone(r["vorgabe_s"])
        self.assertEqual(r["flags"], 0)

    def test_heat_pump_ramps_up_slowly(self):
        """A heat pump (setting) climbs over five minutes to 2.4 kW: steady only after the ramp."""
        a = pr.Anlauf()
        ramp = [200 + 150 * i for i in range(15)]           # 200 ... 2300 W in 280 s
        course = [20] * 5 + ramp + [2400] * 20 + [30] * 3
        [r] = self._run(a, "setting", course)
        self.assertEqual(r["dauer_w"], 2400)
        self.assertEqual(r["spitze_w"], 1550)                # the highest value of the first three minutes
        self.assertEqual(r["stabil_s"], 280)                 # 2300 W is within 10 % of 2400 W, 2150 W is not
        self.assertEqual(r["flags"], 0)

    def test_wallbox_seconds_until_the_setting(self):
        """16 A on three phases = 11 kW: the car takes 1.4, 4, 7, 10.5 kW; 90 % (9.9 kW) after 60 s."""
        a = pr.Anlauf()
        course = [0] * 4 + [(1400, {}), (4000, {}), (7000, {}), (10500, {})] + [11000] * 30 + [0]
        [r] = self._run(a, "wallbox", course, current_a=16.0, phases=3)
        self.assertEqual(r["vorgabe_s"], 60)
        self.assertEqual(r["dauer_w"], 11000)
        self.assertEqual(r["spitze_w"], 11000)

    def test_wallbox_without_phases_and_without_current(self):
        a = pr.Anlauf()
        course = [0] * 4 + [3000, 7000] + [7400] * 30 + [0]
        [r] = self._run(a, "evcc", course, current_a=10.7)    # 7.4 kW at 10.7 A: three phases
        self.assertEqual(r["vorgabe_s"], 20)                 # 7000 W >= 90 % of 3 x 10.7 A x 230 V
        a = pr.Anlauf()
        [r] = self._run(a, "evcc", course)
        self.assertIsNone(r["vorgabe_s"])                     # no setting known

    def test_short_run_and_intervention_and_coarse_sensor(self):
        a = pr.Anlauf()
        course = [0] * 4 + [(1200, {"intervened": True})] + [1000] * 5 + [0, 0]
        [r] = self._run(a, "switch", course, gap_s=45.0)
        self.assertEqual(r["flags"], pr.A_EINGRIFF | pr.A_KURZ | pr.A_GROB)
        self.assertEqual(r["abstand_s"], 45)
        self.assertEqual(r["dauer_w"], 1000)

    def test_restart_while_running_is_no_start(self):
        """The first value after a start of the guard is already high: that is no start (not seen from the beginning)."""
        a = pr.Anlauf()
        self.assertEqual(self._run(a, "switch", [900] * 40 + [0]), [])

    def test_short_dip_is_no_new_start(self):
        """A dip of one cycle ends the run (it is written as short), but the return is no new start."""
        a = pr.Anlauf()
        course = [0] * 4 + [900] * 10 + [0] + [900] * 40 + [0] * 5 + [900] * 35 + [0]
        runs = self._run(a, "switch", course)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["flags"], pr.A_KURZ)
        self.assertEqual(runs[1]["start"], Q + timedelta(seconds=20 * 60))

    def test_change_time_of_the_sensor_is_the_start(self):
        a = pr.Anlauf()
        for i in range(4):
            a.sample("dev", "switch", Q + timedelta(seconds=20 * i), 0)
        a.sample("dev", "switch", Q + timedelta(seconds=80), 900, changed=Q + timedelta(seconds=67))
        run = a.st["dev"]["run"]
        self.assertEqual(run["t0"], Q + timedelta(seconds=67))

    def test_missing_values_and_other_kinds(self):
        a = pr.Anlauf()
        self.assertIsNone(a.sample("b", "battery", Q, 3000))
        self.assertIsNone(a.sample("s", "switch", Q, None))
        self.assertEqual(a.st, {})

    def test_runs_are_kept_per_day(self):
        p = pr.Protokoll()
        a = pr.Anlauf()
        for r in self._run(a, "switch", [0, 0, 0, 0, 1800, 1100] + [900] * 40 + [0]):
            p.add_run("pumpe", r)
        [row] = p.runs("2026-12-01")
        self.assertEqual(row["device"], "pumpe")
        self.assertEqual(row["start_min"], 18 * 60 + 1)
        self.assertEqual((row["spitze_w"], row["dauer_w"]), (1800, 900))
        self.assertEqual(p.runs_count(), 1)


class WithTheGuardTests(unittest.TestCase):
    """Fed from the guard as the coordinator does (`_protokoll_step`): the values of the running quarter hour and the end."""

    def test_rows_from_the_engine(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sim import devices, engine
        g = engine.Guard(devices())
        p = pr.Protokoll()
        t = datetime(2026, 12, 1, 17, 50, 10, tzinfo=TZ)   # started in the middle of a quarter hour: that one is estimated
        while t < datetime(2026, 12, 1, 18, 31, tzinfo=TZ):
            kw = 2.0 if t < datetime(2026, 12, 1, 18, 5, tzinfo=TZ) else 6.0   # the cooker at 18:05
            g.step(t, kw, None, {}, 10.0, 0.5, True)
            if g.finished_quarter_kw is not None:
                p.quarter_end(g.quarter - timedelta(minutes=15), g.finished_quarter_kw, g.finished_estimated)
            p.quarter_tick(t, g.values["quarter"], g.values.get("forecast_kw"), geschaetzt=g.quarter_estimated)
            t += timedelta(seconds=20)
        rows = {r["zeit"]: r for r in p.rows("2026-12-01")}
        self.assertEqual(list(rows), ["17:45", "18:00", "18:15"])
        self.assertEqual(rows["17:45"]["flags"], pr.F_GESCHAETZT)
        r = rows["18:00"]
        self.assertEqual(r["flags"], 0)
        self.assertEqual((r["m1"], r["m3"]), (2.0, 2.0))      # before the cooker: as it is now
        self.assertGreater(r["m10"], 4.0)                       # after it: the projection follows
        self.assertAlmostEqual(r["ende"], 2.0 / 3 + 6.0 * 2 / 3, delta=0.15)
        self.assertEqual(rows["18:15"]["ende"], 6.0)


def _tree(name: str) -> ast.Module:
    return ast.parse((PKG / name).read_text(encoding="utf-8"))


def _method(tree: ast.Module, cls: str, name: str) -> ast.AST:
    c = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return next(n for n in c.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


class StaysLocalTests(unittest.TestCase):
    """Nothing of the log is sent: no network in protokoll.py, only the number of days in the bug report and diagnostics."""

    def test_no_network_in_the_module(self):
        src = (PKG / "protokoll.py").read_text(encoding="utf-8")
        imported = {a.name.split(".")[0] for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.Import, ast.ImportFrom))
                    for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
        self.assertLessEqual(imported, {"__future__", "datetime", "statistics", "typing"})
        self.assertNotIn("http", src)

    def test_bug_report_has_only_the_number_of_days(self):
        node = _method(_tree("coordinator.py"), "Waechter", "build_report")
        used = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "protokoll"}
        self.assertEqual(used, {"days_count"})
        node = ast.parse((PKG / "diagnostics.py").read_text(encoding="utf-8"))
        used = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "protokoll"}
        self.assertEqual(used, {"days_count"})

    def test_bug_report_built_with_a_full_log_has_no_rows(self):
        p = KeepAndSizeTests._fill(3, lambda: 8.75, runs_per_day=4)
        b = fb.bericht("0.15.1", "2026.11.0", {}, {"betriebsart": "active", "protokoll_tage": p.days_count()}, [], [], [], {}, [])
        text = json.dumps(b, ensure_ascii=False)
        self.assertIn('"protokoll_tage": 3', text)
        self.assertNotIn("875", text)
        self.assertNotIn(";", text)
        self.assertIn("protokoll_tage: 3", fb.anzeige(b, True, True))

    def test_saved_bundled_never_in_every_cycle(self):
        """In the cycle only delayed saves, at most every 15 minutes; the guard is never stopped by the log."""
        node = _method(_tree("coordinator.py"), "Waechter", "_protokoll_step")
        calls = {n.func.attr for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn("async_delay_save", calls)
        self.assertNotIn("async_save", calls)
        self.assertNotIn("post", calls)
        self.assertTrue(any(isinstance(n, ast.Try) for n in node.body))
        src = ast.unparse(node)
        self.assertIn("timedelta(minutes=15)", src)
        tick = ast.unparse(_method(_tree("coordinator.py"), "Waechter", "_tick"))
        self.assertIn("self._protokoll_step(now, readings, grid is not None)", tick)

    def test_loaded_safely_and_saved_on_stop(self):
        start = ast.unparse(_method(_tree("coordinator.py"), "Waechter", "async_start"))
        self.assertIn("pr.Protokoll.from_store", start)
        stop = ast.unparse(_method(_tree("coordinator.py"), "Waechter", "async_stop"))
        self.assertIn("self._proto_recent_store.async_save(self.protokoll.recent_data())", stop)
        self.assertIn("self._proto_store.async_save(self.protokoll.archive_data())", stop)


class DisplayTests(unittest.TestCase):
    def test_dashboard_line_and_texts(self):
        import dashboard
        ids = {k: f"{d}.guard_{k}" for k, d in dashboard.ENTITY_KEYS.items()}
        for lang, word in (("de", "Prognose-Protokoll"), ("en", "Forecast log")):
            text = json.dumps(dashboard.build_views(ids, lang), ensure_ascii=False)
            self.assertIn("'protocol_days') | int(0)", text)   # no value (sensor away, before the first day): no line
            self.assertIn(word, text)
        for k in ("protocol", "protocol_days"):
            self.assertTrue(dashboard.TEXTS["de"][k] and dashboard.TEXTS["en"][k], k)

    def test_attribute_name_in_all_translations(self):
        for f in ("strings.json", "translations/en.json", "translations/de.json"):
            d = json.loads((PKG / f).read_text(encoding="utf-8"))
            self.assertIn("name", d["entity"]["sensor"]["forecast_now"]["state_attributes"]["protocol_days"], f)
        src = (PKG / "sensor.py").read_text(encoding="utf-8")
        self.assertIn('"protocol_days": self.waechter.protokoll.days_count()', src)


if __name__ == "__main__":
    unittest.main()
