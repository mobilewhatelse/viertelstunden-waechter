"""0.16.0: the effective limit is shown (user case: limit 4 kW, month peak 9.7 kW, the guard did not step in at 7 kW because it
worked with 9.7 kW, and nothing said so). The switch *Use peak already reached* got a clearer name. Nothing changes in the control."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import sim  # noqa: F401  (puts the integration folder on sys.path)
import explain
from dashboard import ENTITY_KEYS, build_views
from messages import limit_note
from pricing import effective_limit

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
IDS = {k: f"{d}.guard_{k}" for k, d in ENTITY_KEYS.items()}


def _load(rel: str) -> dict:
    return json.loads((PKG / rel).read_text(encoding="utf-8"))


class EffectiveLimitTests(unittest.TestCase):
    def test_user_case(self):
        self.assertEqual(effective_limit(4.0, 9.7, True), 9.7)

    def test_switch_off_keeps_the_set_limit(self):
        self.assertEqual(effective_limit(4.0, 9.7, False), 4.0)

    def test_peak_below_the_limit_changes_nothing(self):
        self.assertEqual(effective_limit(10.0, 7.5, True), 10.0)
        self.assertEqual(effective_limit(10.0, None, True), 10.0)   # no month peak yet


class LimitNoteTests(unittest.TestCase):
    def test_german_sentence_when_raised(self):
        n = limit_note("de", 4.0, 9.7)
        self.assertIn("9,7 kW", n)
        self.assertIn("4,0 kW", n)
        self.assertIn("Monatsspitze", n)

    def test_english_sentence_when_raised(self):
        n = limit_note("en", 4.0, 9.7)
        self.assertIn("9.7 kW", n)
        self.assertIn("month peak", n)

    def test_no_note_when_equal(self):
        self.assertIsNone(limit_note("de", 4.0, 4.0))
        self.assertIsNone(limit_note("en", 10.0, 10.0))


class ExplainTests(unittest.TestCase):
    def test_plain_summary_names_the_effective_limit(self):
        t = explain.plain_summary("de", 0, 7.0, 4.0, "27.11.", effective_kw=9.7)
        self.assertIn("wirksam 9,7 kW", t)
        self.assertIn("Monatsspitze", t)
        self.assertIn("effective 9.7 kW", explain.plain_summary("en", 0, 7.0, 4.0, effective_kw=9.7))

    def test_plain_summary_as_before_without_a_raised_limit(self):
        self.assertEqual(explain.plain_summary("de", 0, 9.08, 10.0, effective_kw=10.0), explain.plain_summary("de", 0, 9.08, 10.0))

    def test_instructions_contain_the_effective_limit(self):
        t = explain.build_instructions("de", "27.11.2026", [], 4.0, 9.2, 7.0, "18:00", 0, 0, False, effective_kw=9.7)
        self.assertIn("9.7 kW", t)
        before = explain.build_instructions("de", "x", [], 10, 9.5, None, None, 1, 0, False)
        self.assertEqual(explain.build_instructions("de", "x", [], 10, 9.5, None, None, 1, 0, False, effective_kw=10.0), before)


class DashboardTests(unittest.TestCase):
    def test_settings_show_the_effective_limit(self):
        for lang, word in (("de", "Wirksame Grenze"), ("en", "Effective limit")):
            main = build_views(IDS, lang)[0]
            cards = [c for s in main["sections"] for c in s["cards"]]
            md = [c["content"] for c in cards if c.get("type") == "markdown" and "effective_limit_kw" in c.get("content", "")]
            self.assertEqual(len(md), 1, lang)
            self.assertIn(word, md[0])
            self.assertIn("limit_note", md[0])
            self.assertIn(IDS["status"], md[0])

    def test_template_renders(self):
        try:
            import jinja2
        except ImportError:
            self.skipTest("jinja2 not installed")

        main = build_views(IDS, "de")[0]
        md = next(c["content"] for s in main["sections"] for c in s["cards"]
                  if c.get("type") == "markdown" and "effective_limit_kw" in c.get("content", ""))
        env = jinja2.Environment()
        for attrs, want, absent in (
                ({"effective_limit_kw": 9.7, "limit_note": "Wirksam 9,7 kW statt 4,0 kW"}, "Wirksam 9,7 kW", None),
                ({"effective_limit_kw": 4.0, "limit_note": None}, "4.0 kW", "None"),
                ({}, "", "None")):   # the status sensor not there yet (restart)
            out = env.from_string(md).render(state_attr=lambda e, a, at=attrs: at.get(a))
            self.assertIn(want, out)
            if absent:
                self.assertNotIn(absent, out)

    def test_new_switch_label_short_enough(self):
        for lang in ("de", "en"):
            tile = next(c for s in build_views(IDS, lang)[0]["sections"] for c in s["cards"] if c.get("entity") == IDS["paid_peak"])
            self.assertIn("Grenze" if lang == "de" else "limit", tile["name"])
            self.assertLessEqual(len(tile["name"]), 32)


class SwitchNameTests(unittest.TestCase):
    def test_clearer_name_in_both_languages(self):
        self.assertEqual(_load("translations/de.json")["entity"]["switch"]["paid_peak"]["name"], "Bereits erreichte Spitze als Grenze nutzen")
        self.assertEqual(_load("translations/en.json")["entity"]["switch"]["paid_peak"]["name"], "Use peak already reached as limit")
        self.assertEqual(_load("strings.json")["entity"]["switch"]["paid_peak"], _load("translations/en.json")["entity"]["switch"]["paid_peak"])

    def test_status_attribute_names_translated(self):
        for f in ("strings.json", "translations/de.json", "translations/en.json"):
            attrs = _load(f)["entity"]["sensor"]["status"].get("state_attributes", {})
            for a in ("effective_limit_kw", "limit_note"):
                self.assertIn(a, attrs, f)


if __name__ == "__main__":
    unittest.main()
