"""Precautionary lock (draft 0.15.2, issue #5): a heat pump with a utility lock contact (device of the kind *change a setting*)
is kept locked while its start would not fit, and freed as soon as there is room. Offline, no Home Assistant needed."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sim import START, engine

R = engine.Reading
LIMIT, MARGIN = 8.0, 0.5   # target 7.5 kW


def hp(**kw):
    d = {"id": "hp", "name": "Wärmepumpe", "kind": "setting", "priority": 10, "start_kw": 5.0, "min_power_w": 100}
    d.update(kw)
    return engine.DeviceConfig.from_dict(d)


class Pump:
    """The heat pump: locked by the guard's battery_release, freed by battery_restore; runs when it wants and is not locked."""

    def __init__(self, wants=False, follows=True):
        self.locked = False
        self.wants = wants
        self.follows = follows

    def reading(self):
        on = self.wants and not self.locked
        return R(power_w=4800.0 if on else 5.0, releasable=not self.locked)

    def apply(self, acts):
        for a in acts:
            if a.device_id == "hp" and a.kind == "battery_release" and self.follows:
                self.locked = True
            elif a.device_id == "hp" and a.kind == "battery_restore":
                self.locked = False


def drive(guard, pump, house_kw, minutes, start=START, log=None):
    """house_kw(t_min) -> kW of the house without the pump; the pump adds its power when it runs."""
    log = [] if log is None else log
    for i in range(int(minutes * 3)):
        t = start + timedelta(seconds=20 * i)
        r = pump.reading()
        grid = house_kw(i / 3.0) + (r.power_w or 0.0) / 1000.0
        acts = guard.step(t, grid, None, {"hp": r}, LIMIT, MARGIN, True)
        pump.apply(acts)
        log += [(i / 3.0, a) for a in acts]
    return log


def texts(log):
    return [a.text for _, a in log if a.text]


class PrecautionTests(unittest.TestCase):
    def test_locked_at_5_5_kw_and_released_when_the_house_falls_to_2_kw(self):
        guard, pump = engine.Guard([hp()]), Pump()
        log = drive(guard, pump, lambda t: 5.5 if t < 10 else 2.0, 20)
        locks = [(t, a) for t, a in log if a.kind == "battery_release"]
        frees = [(t, a) for t, a in log if a.kind == "battery_restore"]
        self.assertEqual(len(locks), 1, texts(log))
        self.assertLess(locks[0][0], 1.0, "locked right away")
        self.assertIn("Vorsorgliche Sperre: Wärmepumpe gesperrt (Spielraum 2.0 kW, Anlauf 5.0 kW)", locks[0][1].text)
        self.assertEqual(len(frees), 1, texts(log))
        self.assertTrue(10.0 <= frees[0][0] <= 11.5, frees[0][0])
        self.assertIn("freigegeben (Spielraum 5.5 kW)", frees[0][1].text)
        self.assertFalse(pump.locked)
        self.assertFalse(guard.interventions, "the normal control is not involved")
        self.assertTrue(all(not a.intervention for _, a in log), "a precautionary lock is no reduction (no push, no count)")

    def test_the_pump_that_wants_to_run_starts_once_there_is_room(self):
        guard, pump = engine.Guard([hp()]), Pump(wants=False)
        drive(guard, pump, lambda t: 5.5, 2)
        self.assertTrue(pump.locked)
        pump.wants = True   # demand comes while it is locked: it must wait
        drive(guard, pump, lambda t: 5.5, 3, start=START + timedelta(minutes=2))
        self.assertTrue(pump.locked)
        log = drive(guard, pump, lambda t: 2.0, 5, start=START + timedelta(minutes=5))
        self.assertFalse(pump.locked)
        self.assertTrue(any(a.kind == "battery_restore" for _, a in log))

    def test_never_longer_than_the_maximum_time_and_then_a_pause(self):
        guard, pump = engine.Guard([hp(start_max_min=30)]), Pump()
        log = drive(guard, pump, lambda t: 5.5, 70)
        locks = [t for t, a in log if a.kind == "battery_release"]
        frees = [t for t, a in log if a.kind == "battery_restore"]
        self.assertEqual(frees[0], 30.0, texts(log))
        self.assertTrue(any("Höchstdauer (30 min)" in x for x in texts(log)))
        self.assertEqual(len(locks), 2, "locked again only after the pause of the same length")
        self.assertGreaterEqual(locks[1], 60.0)

    def test_gap_between_lock_and_release(self):
        guard, pump = engine.Guard([hp(start_gap_min=3)]), Pump()
        log = drive(guard, pump, lambda t: 5.5 if t < 0.5 else 2.0, 6)
        frees = [t for t, a in log if a.kind == "battery_restore"]
        self.assertEqual(len(frees), 1)
        self.assertGreaterEqual(frees[0], 3.0, "not freed before the gap is over, although there was room after a minute")
        # ... and no new lock within the gap after the release
        log = drive(guard, pump, lambda t: 5.5, 4, start=START + timedelta(minutes=frees[0] + 1 / 3))
        locks = [t for t, a in log if a.kind == "battery_release"]
        self.assertEqual(len(locks), 1, texts(log))
        self.assertGreaterEqual(locks[0], 3.0 - 1 / 3 - 0.01, "locked again only 3 minutes after the release")

    def test_a_running_pump_is_never_locked_in_advance(self):
        guard, pump = engine.Guard([hp()]), Pump(wants=True)
        log = drive(guard, pump, lambda t: 1.0, 10)   # 1 + 4.8 kW: below the target, nothing to do
        self.assertEqual(log, [])
        guard2, pump2 = engine.Guard([hp()]), Pump(wants=True)
        log = drive(guard2, pump2, lambda t: 5.5, 10)   # 10.3 kW: too much, but that is the normal control (power_w 0: no lever)
        self.assertFalse([a for _, a in log if a.kind in ("battery_release", "battery_restore")], texts(log))
        self.assertFalse(guard2.precaution)

    def test_running_entity_wins_over_the_power(self):
        guard = engine.Guard([hp()])
        acts = []
        for i in range(3):
            acts += guard.step(START + timedelta(seconds=20 * i), 5.5, None, {"hp": R(power_w=0.0, running=True)}, LIMIT, MARGIN, True)
        self.assertEqual(acts, [])

    def test_observe_mode_sends_nothing_but_says_what_it_would_have_done(self):
        guard, pump = engine.Guard([hp()]), Pump()
        guard.real_effect = False
        log = drive(guard, pump, lambda t: 5.5, 2)
        self.assertTrue(all(a.kind == "log" for _, a in log))
        self.assertIn("hätte vorsorglich gesperrt (Spielraum 2.0 kW, Anlauf 5.0 kW)", " ".join(texts(log)))
        self.assertFalse(pump.locked)
        pump.wants = True   # the start that a lock would have put off
        log = drive(guard, pump, lambda t: 5.5, 1, start=START + timedelta(minutes=2))
        self.assertTrue(any("hätte diesen Anlauf verschoben" in x for x in texts(log)), texts(log))
        self.assertFalse(guard.precaution)

    def test_observe_only_at_the_device_in_active_mode(self):
        guard, pump = engine.Guard([hp(observe_only=True)]), Pump()
        log = drive(guard, pump, lambda t: 5.5 if t < 5 else 2.0, 10)
        self.assertTrue(log)
        self.assertTrue(all(a.kind == "log" for _, a in log))
        self.assertTrue(any("hätte wieder freigegeben" in x for x in texts(log)))

    def test_restart_gives_the_lock_back(self):
        guard, pump = engine.Guard([hp()]), Pump()
        drive(guard, pump, lambda t: 5.5, 2)
        saved = guard.to_dict()
        self.assertIn("hp", saved["precaution"])
        fresh = engine.Guard([hp()])
        fresh.load(saved)
        acts = fresh.release_all(START + timedelta(minutes=3), {"hp": pump.reading()}, "Neustart")
        self.assertEqual([a.kind for a in acts], ["log", "battery_restore"])
        self.assertIn("Alles freigegeben: Neustart", acts[0].text)
        self.assertFalse(fresh.precaution)
        fresh.forget()
        self.assertFalse(fresh.precaution)

    def test_missing_data_and_not_needed_free_the_lock(self):
        guard, pump = engine.Guard([hp()]), Pump()
        drive(guard, pump, lambda t: 5.5, 2)
        acts = guard.step(START + timedelta(minutes=2, seconds=20), 5.5, None, {"hp": pump.reading()}, LIMIT, MARGIN, False)
        self.assertEqual([a.kind for a in acts], ["log", "battery_restore"])
        guard2, pump2 = engine.Guard([hp()]), Pump()
        drive(guard2, pump2, lambda t: 5.5, 2)
        acts = []
        for i in range(8):
            acts += guard2.step(START + timedelta(minutes=2, seconds=20 * i), None, None, {"hp": pump2.reading()}, LIMIT, MARGIN, True)
        self.assertIn("battery_restore", [a.kind for a in acts])

    def test_a_lock_of_the_utility_is_never_touched(self):
        guard = engine.Guard([hp()])
        acts = []
        for i in range(30):   # the contact is already at its "locked" value (the real utility lock): releasable False
            acts += guard.step(START + timedelta(seconds=20 * i), 5.5, None, {"hp": R(power_w=0.0, releasable=False)}, LIMIT, MARGIN, True)
        self.assertEqual(acts, [])

    def test_without_power_sensor_never_locked_said_once(self):
        guard = engine.Guard([hp()])
        acts = []
        for i in range(30):
            acts += guard.step(START + timedelta(seconds=20 * i), 5.5, None, {"hp": R()}, LIMIT, MARGIN, True)
        self.assertEqual([a.kind for a in acts], ["log"])
        self.assertIn("keinen Leistungssensor", acts[0].text)

    def test_a_lock_that_does_not_show_is_given_up(self):
        guard, pump = engine.Guard([hp()]), Pump(follows=False)
        log = drive(guard, pump, lambda t: 5.5, 5)
        self.assertTrue(any("nicht übernommen" in x for x in texts(log)), texts(log))
        self.assertEqual(len([a for _, a in log if a.kind == "battery_release"]), 1, "not tried again every cycle")

    def test_comfort_value_below_its_minimum_is_never_kept_from_starting(self):
        guard = engine.Guard([hp(comfort_min=45)])
        acts = []
        for i in range(6):
            acts += guard.step(START + timedelta(seconds=20 * i), 5.5, None, {"hp": R(power_w=0.0, soc=40.0)}, LIMIT, MARGIN, True)
        self.assertEqual(acts, [])

    def test_off_is_the_behaviour_of_before(self):
        """Field 0 (or missing): the same actions and values as without the draft, the step never reaches the new code."""
        def scenario(dev):
            guard = engine.Guard([dev], engine.STRATEGY_ORDER)
            out = []
            for i in range(40):
                grid = 9.0 if i < 20 else 2.0
                out += [(a.kind, a.text) for a in guard.step(START + timedelta(seconds=20 * i), grid, None,
                                                               {"hp": R(power_w=0.0, releasable="hp" not in guard.interventions)},
                                                               5.0, 0.5, True)]
            return out, guard
        base = {"id": "hp", "name": "WP", "kind": "setting", "priority": 2, "power_w": 2000}
        old, g_old = scenario(engine.DeviceConfig.from_dict(base))
        off, g_off = scenario(engine.DeviceConfig.from_dict({**base, "start_kw": 0}))
        self.assertEqual(old, off)
        self.assertTrue(any(k == "battery_release" for k, _ in old))
        self.assertNotIn("precaution", g_off.values)
        self.assertEqual(g_off.to_dict(), {"interventions": g_off.interventions})
        self.assertEqual(engine.DeviceConfig.from_dict(base).start_kw, 0.0)

    def test_other_kinds_are_not_locked_yet(self):
        sw = engine.DeviceConfig.from_dict({"id": "hp", "name": "WP", "kind": "switch", "start_kw": 5.0})
        guard = engine.Guard([sw])
        acts = []
        for i in range(6):
            acts += guard.step(START + timedelta(seconds=20 * i), 5.5, None, {"hp": R(power_w=0.0, is_on=True)}, LIMIT, MARGIN, True)
        self.assertEqual(acts, [])


class DashboardTests(unittest.TestCase):
    def test_card_only_with_a_device_that_uses_it_and_robust_without_the_attribute(self):
        import json

        from dashboard import ENTITY_KEYS, build_views
        ids = {k: f"{d}.guard_{k}" for k, d in ENTITY_KEYS.items()}
        for lang in ("de", "en"):
            self.assertEqual(json.dumps(build_views(ids, lang)), json.dumps(build_views(ids, lang, precaution=False)))
            self.assertNotIn("precaution", json.dumps(build_views(ids, lang)))
        views = build_views(ids, "de", precaution=True)
        cards = [c for v in views for s in v["sections"] for c in s["cards"] if c.get("title") == "Vorsorgliche Sperre (Entwurf)"]
        self.assertEqual(len(cards), 1)
        try:
            import jinja2
        except ImportError:
            self.skipTest("jinja2 not installed")
        tpl = jinja2.Environment().from_string(cards[0]["content"])
        for attr, want in ((None, "Kein Gerät mit Anlaufleistung"),
                           ([{"name": "WP", "start_kw": 5.0, "locked": True, "observed": False, "suggestion":
                              "Gemessene Anlaufspitze: 4.6 kW (Median aus 7 Läufen)"}], "**WP**: Anlauf 5.0 kW · jetzt vorsorglich gesperrt · Gemessene"),
                           ([{"name": "WP", "start_kw": None, "locked": False, "observed": False, "suggestion": None}],
                            "Anlaufleistung nicht eingetragen")):
            out = tpl.render(state_attr=lambda e, a, v=attr: v if a == "precaution" else None)
            self.assertIn(want, out)


def _coordinator_method(name):
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter" / "coordinator.py").read_text(encoding="utf-8")
    cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "Waechter")
    return next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


class CoordinatorTests(unittest.TestCase):
    """The coordinator needs Home Assistant; its methods are read from the source (as in test_prognose_glatt)."""

    def test_restart_gives_back_a_lock_from_before_and_the_store_holds_it_only_while_held(self):
        import ast
        start = ast.unparse(_coordinator_method("async_start"))
        self.assertIn("data.get('interventions') or data.get('precaution')", start)
        self.assertIn("'precaution': data.get('precaution') or {}", start)
        self.assertIn("release_all", start)
        self.assertIn("self.guard.interventions or self.guard.precaution", ast.unparse(_coordinator_method("async_stop")))
        data = ast.unparse(_coordinator_method("_data"))
        self.assertIn("if self.executing and self.guard.precaution else {}", data)

    def test_nothing_new_is_sent(self):
        """A setting device had no power sensor before: the device check and the overview of the setup stay as they were."""
        import ast
        self.assertIn("power_w=None if kind == KIND_SETTING else r.power_w", ast.unparse(_coordinator_method("_check_samples")))
        self.assertIn("key in PRECAUTION_ENTITIES and d.get(D_KIND) == KIND_SETTING", ast.unparse(_coordinator_method("_check_info")))
        self.assertIn("k in PRECAUTION_ENTITIES", ast.unparse(_coordinator_method("setup_overview")))

    def test_precaution_info_suggests_but_never_sets(self):
        import ast
        from types import SimpleNamespace

        import messages
        import protokoll as pr
        node = _coordinator_method("precaution_info")
        node.returns = None
        node.args.args[0].annotation = None
        now = datetime(2026, 12, 2, 8, 0)
        ns = {"Any": object, "KIND_SETTING": "setting", "D_KIND": "kind", "D_NAME": "name", "D_START_KW": "start_kw",
              "dt_util": SimpleNamespace(now=lambda: now)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "coordinator.py", "exec"), ns)  # noqa: S102
        p = pr.Protokoll()
        for i, w in enumerate((4400, 4600, 5100)):
            p.add_run("hp", {"start": now - timedelta(hours=5 - i), "spitze_w": w, "dauer_w": 2400, "flags": 0})
        guard = engine.Guard([hp()])
        w = SimpleNamespace(protokoll=p, guard=guard, t=messages.Messages("de"),
                            raw_devices={"hp": {"kind": "setting", "name": "WP", "start_kw": 0},
                                         "sw": {"kind": "switch", "name": "Pool"}})
        info = ns["precaution_info"](w)
        self.assertEqual(info, [{"name": "WP", "start_kw": None, "locked": False, "observed": False, "suggestion_kw": 4.6,
                                 "runs": 3, "suggestion": "Gemessene Anlaufspitze: 4.6 kW (Median aus 3 Läufen)"}])
        self.assertEqual(w.raw_devices["hp"]["start_kw"], 0, "never taken over by itself")
        w.protokoll = pr.Protokoll()
        self.assertEqual(ns["precaution_info"](w), [], "no start power and nothing measured: no attribute")


class ConfigFlowTests(unittest.TestCase):
    def _fn(self):
        import ast
        from pathlib import Path
        pkg = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
        tree = ast.parse((pkg / "config_flow.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_precaution_errors")
        node.returns = None
        node.args.args[0].annotation = None
        ns = {"D_START_KW": "start_kw", "D_POWER": "power_entity", "D_RUNNING": "running_entity",
              "D_RESTORE_ORIG": "restore_original", "D_OFF_SCRIPT": "off_script"}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "config_flow.py", "exec"), ns)  # noqa: S102
        return ns["_precaution_errors"], pkg

    def test_fields_and_errors(self):
        import json
        fn, pkg = self._fn()
        self.assertEqual(fn({"start_kw": 0}), {})
        self.assertEqual(fn({"start_kw": 5}), {"start_kw": "start_needs_sensor"})
        self.assertEqual(fn({"start_kw": 5, "power_entity": "sensor.wp"}), {})
        self.assertEqual(fn({"start_kw": 5, "running_entity": "binary_sensor.wp", "restore_original": False}),
                         {"start_kw": "start_needs_restore"})
        self.assertEqual(fn({"start_kw": 5, "running_entity": "binary_sensor.wp", "restore_original": False, "off_script": "script.x"}), {})
        for f in ("strings.json", "translations/de.json", "translations/en.json"):
            s = json.loads((pkg / f).read_text(encoding="utf-8"))["config_subentries"]["setting"]
            for step in ("user", "reconfigure"):
                for key in ("start_kw", "power_entity", "power_invert", "min_power_w", "running_entity", "start_max_min", "start_gap_min"):
                    self.assertIn(key, s["step"][step]["data"], (f, step, key))
                    self.assertIn(key, s["step"][step]["data_description"], (f, step, key))
            self.assertIn("start_needs_sensor", s["error"])
            self.assertIn("start_needs_restore", s["error"])
            other = json.loads((pkg / f).read_text(encoding="utf-8"))["config_subentries"]["switch"]["step"]["user"]["data"]
            self.assertNotIn("start_kw", other, "only at the kind change a setting for now")


class SuggestionTests(unittest.TestCase):
    def test_median_of_the_measured_peaks(self):
        import protokoll as pr
        p = pr.Protokoll()
        day = datetime(2026, 12, 1, 6, 0)
        for i, w in enumerate((4400, 4600, 5100)):
            p.add_run("hp", {"start": day + timedelta(hours=i), "spitze_w": w, "dauer_w": 2400, "flags": 0})
        p.add_run("other", {"start": day, "spitze_w": 9000, "dauer_w": 9000, "flags": 0})
        p.add_run("hp", {"start": day + timedelta(hours=5), "spitze_w": 2500, "dauer_w": 2400, "flags": pr.A_GROB})  # coarse: left out
        s = p.start_peak("hp", day + timedelta(days=1))
        self.assertEqual(s, {"kw": 4.6, "n": 3})
        self.assertIsNone(p.start_peak("hp", day + timedelta(days=1), min_runs=4))
        self.assertIsNone(p.start_peak("nobody", day))
        self.assertIsNone(p.start_peak("hp", day + timedelta(days=60)), "only the last 30 days")


if __name__ == "__main__":
    unittest.main()
