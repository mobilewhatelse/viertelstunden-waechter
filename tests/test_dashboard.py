"""Tests for the generated dashboard (structure and template syntax, no Home Assistant needed)."""

from __future__ import annotations

import json
import unittest

import sim  # noqa: F401  (puts the integration folder on sys.path)
from dashboard import ENTITY_KEYS, build_views

IDS = {k: f"{d}.guard_{k}" for k, d in ENTITY_KEYS.items()}


def _cards(views):
    for v in views:
        for s in v["sections"]:
            yield from s["cards"]


class DashboardTests(unittest.TestCase):
    def test_three_views_in_both_languages(self):
        for lang in ("de", "en", "de_AT"):
            views = build_views(IDS, lang)
            self.assertEqual([v["path"] for v in views], ["waechter", "heute", "statistik"])
            json.dumps(views)  # must be serialisable for the storage

    def test_every_entity_is_used_and_nothing_else_is_referenced(self):
        """Every entity except the intermediate values left out on purpose (fewer cards, graphics first)."""
        hidden = {"allowed", "quarter_energy", "cost_without", "saved_now"}
        views = build_views(IDS, "en")
        text = json.dumps(views)
        for key, entity_id in IDS.items():
            if key in hidden:
                self.assertNotIn(entity_id, text, key)
            else:
                self.assertIn(entity_id, text, key)
        import re

        used = set(re.findall(r"\b(?:sensor|number|select|switch)\.[a-z0-9_]+", text))
        self.assertLessEqual(used, set(IDS.values()))

    def test_grid_import_now_right_below_the_status_in_both_views(self):
        """Feedback 13.11.2026: the current grid import was missing. With the measured sensor it is a tile after the status."""
        for lang, name in (("de", "Netzbezug jetzt"), ("en", "Grid import now")):
            views = build_views({**IDS, "grid_power_sensor": "sensor.netz"}, lang)
            for path in ("waechter", "heute"):
                cards = [c for v in views if v["path"] == path for sec in v["sections"] for c in sec["cards"]]
                ents = [c.get("entity") for c in cards]
                self.assertIn("sensor.netz", ents, path)
                i = ents.index("sensor.netz")
                self.assertEqual(ents[i - 1], IDS["status"], path)
                self.assertEqual(cards[i]["name"], name)
        without = json.dumps(build_views(IDS, "de"))
        self.assertNotIn("Netzbezug jetzt", without)   # no sensor (only evcc): no empty tile

    def test_markdown_templates_parse(self):
        try:
            import jinja2
        except ImportError:  # the templates are checked against Home Assistant after the update
            self.skipTest("jinja2 not installed")
        env = jinja2.Environment()
        for card in _cards(build_views(IDS, "de")):
            if card["type"] == "markdown":
                env.parse(card["content"])

    def test_charts_are_svg_images_without_unresolved_placeholders(self):
        import re

        import dashboard_charts as charts

        cards = [
            charts.forecast(IDS, "Target", "legend", "none"),
            charts.profile(IDS, "Mo,Tu,We,Th,Fr,Sa,Su", "Typical|Highest|Hour", "legend", "none"),
            charts.daily(IDS, "Limit", "legend", "none"),
            charts.months(IDS, "Limit", "legend", "none"),
            charts.now_bar(IDS, "Forecast / target", "legend"),
            charts.today_quarters(IDS, "Limit", "legend", "none"),
        ]
        for content in cards:
            self.assertIn("data:image/svg+xml", content)
            self.assertIsNone(re.search(r"@[A-Z0-9]+@", content), content[:200])
        try:
            import jinja2
        except ImportError:
            return
        env = jinja2.Environment()
        for content in cards:
            env.parse(content)

    def test_statistics_view_contains_the_charts(self):
        for lang in ("de", "en"):
            views = {v["path"]: v for v in build_views(IDS, lang)}
            self.assertEqual(json.dumps(views["statistik"]).count("data:image/svg+xml"), 4)
            # the compact view for the phone: status, forecast bar and the quarter hours of today
            heute = json.dumps(views["heute"])
            self.assertEqual(heute.count("data:image/svg+xml"), 2)
            self.assertEqual(views["heute"]["max_columns"], 1)
            for key in ("status", "mode", "today_peak", "month_peak", "interventions_today", "last_quarter", "ai_explanation"):
                self.assertIn(IDS[key], heute, key)

    def test_with_a_car_planner_its_plan_is_shown_and_the_own_plan_steps_back(self):
        planners = [{"name": "Car", "plan": "sensor.car_charge_plan", "ready": "sensor.car_ready"}]
        for lang in ("de", "en"):
            views = {v["path"]: v for v in build_views(IDS, lang, planners)}
            stats = json.dumps(views["statistik"], ensure_ascii=False)
            self.assertIn("sensor.car_charge_plan", stats)
            self.assertNotIn("sensor.car_ready", stats)                         # readiness is on the planner's own dashboard
            self.assertNotIn(f'"entity": "{IDS["charge_plan"]}"', stats)       # the own plan tile is gone
            self.assertNotIn(IDS["charge_plan_enabled"], stats)                 # no own plan, no own plan switches: either the planner or the guard
            self.assertNotIn(IDS["charge_plan_execute"], stats)
        try:
            import jinja2
        except ImportError:
            return
        env = jinja2.Environment()
        for card in _cards(build_views(IDS, "de", planners + [{"name": "Two", "plan": "sensor.two_plan", "ready": None}])):
            if card["type"] == "markdown":
                env.parse(card["content"])

    def test_without_a_planner_the_dashboard_is_as_before(self):
        self.assertEqual(json.dumps(build_views(IDS, "en", [])), json.dumps(build_views(IDS, "en")))
        self.assertIn(f'"entity": "{IDS["charge_plan"]}"', json.dumps(build_views(IDS, "en")))

    def test_settings_are_full_width_tiles_so_the_names_are_not_cut_off(self):
        """Field 17.11.2026 (phone): in entities rows the names were cut off ('Leistungspreis bis z…'). Now one full-width tile per
        setting with a short name; numbers with +/-, selections with their options, switches toggle on a tap."""
        keys = ("mode", "strategy", "limit", "margin", "paid_peak", "notify_intervention", "costs_enabled", "forecast_enabled",
                "predictive", "battery_reserve", "ai_explainer", "prewarn", "weekly_report_enabled", "price_low", "price_high",
                "price_threshold", "weather_enabled", "share_usage", "charge_plan_enabled", "charge_plan_execute")
        for lang in ("de", "en"):
            cards = list(_cards(build_views(IDS, lang)))
            for k in keys:
                tiles = [c for c in cards if c.get("type") == "tile" and c.get("entity") == IDS[k]]
                self.assertTrue(tiles, k)
                for t in tiles:
                    self.assertEqual(t["grid_options"], {"columns": "full"}, k)
                    self.assertLessEqual(len(t["name"]), 32, t["name"])
                    kind = IDS[k].split(".")[0]
                    if kind == "number":
                        self.assertEqual(t["features"][0]["type"], "numeric-input", k)
                    elif kind == "select":
                        self.assertEqual(t["features"][0]["type"], "select-options", k)
                    else:
                        self.assertEqual(t["tap_action"], {"action": "toggle"}, k)
            # the feedback card keeps its short list (text field, send buttons, sharing): a text field needs an entities row
            self.assertFalse([c for c in cards if c.get("type") == "entities"
                              and not any(e.get("entity", "").startswith("text.") for e in c.get("entities", []))
                              and any(e.get("entity") in [IDS[k] for k in keys] for e in c.get("entities", []))])

    def test_titled_entities_cards_have_no_header_toggle(self):
        """The header toggle of an entities card flips all its switches at once (it could switch on "carry out the plan")."""
        for planners in (None, [{"name": "Car", "plan": "sensor.car_charge_plan", "ready": None}]):
            for card in _cards(build_views(IDS, "en", planners)):
                if card["type"] == "entities" and card.get("title"):
                    self.assertIs(card.get("show_header_toggle"), False, card["title"])
    def test_german_text_in_german_installations(self):
        self.assertEqual(build_views(IDS, "de")[0]["title"], "Wächter")
        self.assertEqual(build_views(IDS, "en")[0]["title"], "Guard")


class MissingSensorTests(unittest.TestCase):
    """18.11.2026: right after a restart the dashboard drew before the status sensor was back - 'None' has no attribute
    'attributes' in the log. `is defined` does not help (a missing entity is None, which is defined): the guard must test it."""

    def test_no_unguarded_attribute_access(self):
        import re

        text = json.dumps(build_views(IDS, "de", evcc=True))
        self.assertNotIn("is defined else {}", text)
        bare = [m.group(0) for m in re.finditer(r"states(\[[^\]]+\]|\.[a-z_]+\.[a-z0-9_]+)\.attributes(?! if states)", text)]
        self.assertEqual(bare, [])


if __name__ == "__main__":
    unittest.main()


class SourcesCardTests(unittest.TestCase):
    """User 2026-11-09: the card 'Sources compared' is shipped, but only shown when evcc is entered."""

    @staticmethod
    def _sources(views):
        return [c for c in _cards(views) if c.get("type") == "markdown" and ("Quellen im Vergleich" in c["content"] or "Sources compared" in c["content"])]

    def test_without_evcc_there_is_no_card(self):
        for lang in ("de", "en"):
            self.assertEqual(self._sources(build_views(IDS, lang)), [])

    def test_with_evcc_there_is_exactly_one_card(self):
        for lang, word in (("de", "Ihr Sensor"), ("en", "Your sensor")):
            cards = self._sources(build_views({**IDS, "grid_power_sensor": "sensor.grid"}, lang, evcc=True))
            self.assertEqual(len(cards), 1)
            self.assertIn(word, cards[0]["content"])
            self.assertIn("grid_evcc_kw", cards[0]["content"])

    def test_with_evcc_but_without_own_sensor_the_card_still_builds(self):
        cards = self._sources(build_views(IDS, "de", evcc=True))
        self.assertEqual(len(cards), 1)
        self.assertNotIn("@GP@", cards[0]["content"])
