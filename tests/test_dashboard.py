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
    def test_two_views_in_both_languages(self):
        for lang in ("de", "en", "de_AT"):
            views = build_views(IDS, lang)
            self.assertEqual([v["path"] for v in views], ["waechter", "statistik"])
            json.dumps(views)  # must be serialisable for the storage

    def test_every_entity_is_used_and_nothing_else_is_referenced(self):
        views = build_views(IDS, "en")
        text = json.dumps(views)
        for key, entity_id in IDS.items():
            self.assertIn(entity_id, text, key)
        import re

        used = set(re.findall(r"\b(?:sensor|number|select|switch)\.[a-z0-9_]+", text))
        self.assertLessEqual(used, set(IDS.values()))

    def test_markdown_templates_parse(self):
        try:
            import jinja2
        except ImportError:  # the templates are checked against Home Assistant after the update
            self.skipTest("jinja2 not installed")
        env = jinja2.Environment()
        for card in _cards(build_views(IDS, "de")):
            if card["type"] == "markdown":
                env.parse(card["content"])

    def test_german_text_in_german_installations(self):
        self.assertEqual(build_views(IDS, "de")[0]["title"], "Wächter")
        self.assertEqual(build_views(IDS, "en")[0]["title"], "Guard")


if __name__ == "__main__":
    unittest.main()
