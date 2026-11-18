"""Charts full width (vollbild.py): a tap on a chart opens a subview of the dashboard with that card over the whole width."""

import json
import sys
import unittest
from pathlib import Path

import sim  # noqa: F401,E402  (puts the integration folder on sys.path)
import dashboard  # noqa: E402
import vollbild as vb  # noqa: E402

CHART = "{% set c = state_attr('sensor.x', 'chart') %}{% if c %}![](data:image/svg+xml;utf8,{{ c | urlencode }}){% endif %}\n\nLegend"


def config():
    return {"views": [{"path": "main", "sections": [{"cards": [
        {"type": "heading", "heading": "Ladeplan"},
        {"type": "markdown", "content": CHART},
        {"type": "markdown", "content": "only text"},
        {"type": "tile", "entity": "sensor.y"}]}]}]}


def real(language: str = "de") -> dict:
    ids = {k: f"{d}.guard_{k}" for k, d in dashboard.ENTITY_KEYS.items()}
    return {"views": dashboard.build_views(ids, language, evcc=True)}


class SubviewTests(unittest.TestCase):
    def test_a_chart_links_to_its_subview(self):
        c = config()
        ids = vb.link_charts(c, "de")
        self.assertEqual(len(ids), 1)
        card = c["views"][0]["sections"][0]["cards"][1]["content"]
        self.assertIn(f'<a href="grafik-{ids[0]}">![](data:image/svg+xml;utf8,', card)
        self.assertNotIn("target=", card)   # a relative link without target: the dashboard switches, the app is not loaded again

    def test_the_subview_shows_the_whole_card_with_its_caption(self):
        c = config()
        cid = vb.link_charts(c, "de")[0]
        sub = c["views"][-1]
        self.assertEqual(sub["path"], f"grafik-{cid}")
        self.assertTrue(sub["subview"])
        self.assertEqual(sub["type"], "panel")
        self.assertEqual(sub["title"], "Ladeplan")   # the heading above the chart
        self.assertEqual(sub["cards"], [{"type": "markdown", "content": CHART}])   # chart and legend, no link in it

    def test_text_and_other_cards_stay(self):
        c = config()
        vb.link_charts(c)
        cards = c["views"][0]["sections"][0]["cards"]
        self.assertEqual(cards[2]["content"], "only text")
        self.assertEqual(cards[3], {"type": "tile", "entity": "sensor.y"})

    def test_the_same_card_gets_the_same_subview(self):
        self.assertEqual(vb.link_charts(config()), vb.link_charts(config()))

    def test_every_chart_of_the_real_dashboard(self):
        c = real()
        before = json.dumps(c).count("data:image/svg+xml")
        ids = vb.link_charts(c, "de")
        subs = [v for v in c["views"] if v.get("subview")]
        self.assertGreaterEqual(len(subs), 4)
        self.assertEqual(len(subs), len(ids))
        main = json.dumps([v for v in c["views"] if not v.get("subview")])
        self.assertEqual(main.count('<a href=\\"grafik-'), before)
        for v in subs:
            self.assertIn("data:image/svg+xml", v["cards"][0]["content"])
            self.assertTrue(v["title"])

    def test_no_page_outside_the_dashboard(self):
        self.assertNotIn("/api/", json.dumps(real()))
        c = real()
        vb.link_charts(c)
        self.assertNotIn("/api/", json.dumps(c))


if __name__ == "__main__":
    unittest.main()
