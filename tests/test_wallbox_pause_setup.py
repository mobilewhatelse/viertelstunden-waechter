"""Wallbox may pause as the last measure (BETA, 0.16.0): fields, texts, checks of the settings, dashboard and status attribute.

config_flow.py and coordinator.py import Home Assistant, so their functions are read from the source (ast), as in test_vorsorge."""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

import sim  # noqa: F401  (puts the integration folder on sys.path)
from dashboard import ENTITY_KEYS, build_views
import messages

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
FILES = ("strings.json", "translations/de.json", "translations/en.json")
IDS = {k: f"{d}.guard_{k}" for k, d in ENTITY_KEYS.items()}
WALLBOX_STEPS = (("config", "step", "add_wallbox"), ("config_subentries", "wallbox", "step", "user"),
                 ("config_subentries", "wallbox", "step", "reconfigure"))
EVCC_STEPS = (("config", "step", "evcc_device"), ("config_subentries", "evcc", "step", "user"),
              ("config_subentries", "evcc", "step", "reconfigure"))
COMMON = ("may_pause", "hold_min", "pause_min")
COMMANDS = ("pause_entity", "pause_value", "resume_entity", "resume_value")


def _get(d, path):
    for p in path:
        d = d[p]
    return d


def _fn(module: str, name: str, ns: dict):
    tree = ast.parse((PKG / module).read_text(encoding="utf-8"))
    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    node = nodes[0]
    node.decorator_list = []
    node.returns = None
    for a in node.args.args:
        a.annotation = None
    exec(compile(ast.Module(body=[node], type_ignores=[]), module, "exec"), ns)  # noqa: S102
    return ns[name]


CONST = {"D_MAY_PAUSE": "may_pause", "D_WB_PAUSE": "pause_entity", "D_WB_PAUSE_VALUE": "pause_value",
         "D_WB_RESUME": "resume_entity", "D_WB_RESUME_VALUE": "resume_value", "D_KIND": "kind", "KIND_WALLBOX": "wallbox",
         "KIND_EVCC": "evcc", "D_EVCC_ONE_PHASE": "evcc_one_phase", "Any": object}


class TextTests(unittest.TestCase):
    def test_fields_in_every_language_and_step(self):
        for f in FILES:
            s = json.loads((PKG / f).read_text(encoding="utf-8"))
            for path in WALLBOX_STEPS + EVCC_STEPS:
                step = _get(s, path)
                keys = COMMON + (COMMANDS if path in WALLBOX_STEPS else ())
                for key in keys:
                    self.assertIn(key, step["data"], (f, path, key))
                    self.assertIn(key, step["data_description"], (f, path, key))
                label = step["data"]["may_pause"] + " " + step["data_description"]["may_pause"]
                self.assertIn("Beta", label, (f, path))
                if path not in WALLBOX_STEPS:
                    for key in COMMANDS:
                        self.assertNotIn(key, step["data"], "evcc pauses with its mode, no commands")
            for err in (_get(s, ("config", "error")), _get(s, ("config_subentries", "wallbox", "error"))):
                for key in ("pause_needs_commands", "pair", "value_onoff", "value_number", "unknown_option"):
                    self.assertIn(key, err, (f, key))

    def test_de_is_german(self):
        s = json.loads((PKG / "translations/de.json").read_text(encoding="utf-8"))
        self.assertIn("letzte Maßnahme", _get(s, WALLBOX_STEPS[1])["data"]["may_pause"])
        self.assertIn("Nur beobachten", _get(s, EVCC_STEPS[1])["data_description"]["may_pause"])

    def test_messages_in_both_languages(self):
        for key in ("wb_pause", "wb_would_pause", "wb_resume", "wb_resume_now", "wb_pause_user", "wb_pause_kept", "still_charging"):
            self.assertIn(key, messages.MESSAGES["de"], key)
            self.assertIn(key, messages.MESSAGES["en"], key)
        t = messages.Messages("de")
        self.assertIn("pausiert", t("wb_pause", name="Wallbox", excess=1.2, kw=4.1))
        self.assertIn("Mindeststrom reicht nicht", t("wb_pause", name="Wallbox", excess=1.2, kw=4.1))
        self.assertIn("wieder erlaubt", t("wb_resume", name="Wallbox", room=5.0))


class SettingsCheckTests(unittest.TestCase):
    def setUp(self):
        self.opts = {"select.wb_mode": ["Laden", "Pause"]}
        self.fn = _fn("config_flow.py", "_pause_errors", dict(CONST))

    def check(self, u):
        return self.fn(u, lambda eid: self.opts.get(eid))

    def test_off_needs_nothing(self):
        self.assertEqual(self.check({}), {})
        self.assertEqual(self.check({"may_pause": False}), {})

    def test_on_needs_both_commands(self):
        self.assertEqual(self.check({"may_pause": True}), {"may_pause": "pause_needs_commands"})
        self.assertEqual(self.check({"may_pause": True, "pause_entity": "switch.wb"}), {"may_pause": "pause_needs_commands"})
        self.assertEqual(self.check({"may_pause": True, "pause_entity": "switch.wb", "pause_value": "off",
                                     "resume_entity": "switch.wb", "resume_value": "on"}), {})
        self.assertEqual(self.check({"may_pause": True, "pause_entity": "button.wb_stop", "resume_entity": "button.wb_start"}), {})

    def test_values_fit_the_entity(self):
        base = {"may_pause": True, "resume_entity": "button.go"}
        self.assertEqual(self.check({**base, "pause_entity": "switch.wb"}), {"pause_value": "pair"})
        self.assertEqual(self.check({**base, "pause_entity": "switch.wb", "pause_value": "aus"}), {"pause_value": "value_onoff"})
        self.assertEqual(self.check({**base, "pause_entity": "number.wb_a", "pause_value": "x"}), {"pause_value": "value_number"})
        self.assertEqual(self.check({**base, "pause_entity": "select.wb_mode", "pause_value": "Stopp"}), {"pause_value": "unknown_option"})
        self.assertEqual(self.check({**base, "pause_entity": "select.wb_mode", "pause_value": "Pause"}), {})
        self.assertEqual(self.check({**base, "pause_entity": "number.wb_a", "pause_value": "0"}), {})

    def test_used_in_the_setup_and_in_the_device_dialog(self):
        src = (PKG / "config_flow.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count("_pause_errors("), 3, "definition, set-up assistant and the wallbox dialog")


class EngineDictTests(unittest.TestCase):
    def setUp(self):
        self.fn = _fn("coordinator.py", "_engine_dict", dict(CONST))

    def test_an_older_wallbox_stays_as_it_was(self):
        d = {"kind": "wallbox", "name": "WB"}
        self.assertIs(self.fn(d), d)
        self.assertNotIn("may_pause", self.fn(d))

    def test_wallbox_without_commands_can_never_pause(self):
        self.assertFalse(self.fn({"kind": "wallbox", "may_pause": True})["may_pause"])
        self.assertTrue(self.fn({"kind": "wallbox", "may_pause": True, "pause_entity": "button.a", "resume_entity": "button.b"})["may_pause"])

    def test_evcc_pauses_with_its_mode(self):
        out = self.fn({"kind": "evcc", "may_pause": True})
        self.assertEqual(out["kind"], "wallbox")
        self.assertTrue(out["may_pause"])
        self.assertTrue(out["pause_by_mode"], "evcc: paused only with a known mode")
        self.assertFalse(self.fn({"kind": "evcc"}).get("may_pause", False))
        self.assertNotIn("pause_by_mode", self.fn({"kind": "wallbox", "may_pause": True, "pause_entity": "button.a",
                                                   "resume_entity": "button.b"}))


class ShownTests(unittest.TestCase):
    def _md(self, lang):
        main = build_views(IDS, lang)[0]
        return next(c["content"] for s in main["sections"] for c in s["cards"]
                    if c.get("type") == "markdown" and "paused_by_guard" in c.get("content", ""))

    def test_dashboard_line_only_while_paused(self):
        try:
            import jinja2
        except ImportError:
            self.skipTest("jinja2 not installed")
        for lang, word in (("de", "vom Wächter pausiert"), ("en", "paused by the guard")):
            md = self._md(lang)
            render = lambda attrs: jinja2.Environment().from_string(md).render(state_attr=lambda e, a: attrs.get(a))  # noqa: E731
            self.assertIn(word, render({"paused_by_guard": ["eGolf"]}))
            self.assertIn("eGolf", render({"paused_by_guard": ["eGolf"]}))
            self.assertNotIn(word, render({}))
            self.assertNotIn(word, render({"paused_by_guard": []}))

    def test_status_attribute_and_bug_report(self):
        sensor = (PKG / "sensor.py").read_text(encoding="utf-8")
        self.assertIn('"paused_by_guard"', sensor)
        coord = (PKG / "coordinator.py").read_text(encoding="utf-8")
        self.assertIn('g["pausiert"]', coord, "bug report: the device says it is paused by the guard")
        self.assertIn('"wb_pause"', coord)


if __name__ == "__main__":
    unittest.main()
