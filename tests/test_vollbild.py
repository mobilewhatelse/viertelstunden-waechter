"""Charts full screen (vollbild.py): every chart of the dashboard links to a page that may be zoomed on the phone."""

import sys
import unittest
from pathlib import Path

import sim  # noqa: F401,E402  (puts the integration folder on sys.path)
import dashboard  # noqa: E402
import vollbild as vb  # noqa: E402

CHART = "{% set c = state_attr('sensor.x', 'chart') %}{% if c %}![](data:image/svg+xml;utf8,{{ c | urlencode }}){% endif %}"


class LinkTests(unittest.TestCase):
    def _views(self):
        return [{"sections": [{"cards": [{"type": "markdown", "content": CHART},
                                         {"type": "markdown", "content": "only text"},
                                         {"type": "tile", "entity": "sensor.y"}]}]}]

    def test_a_chart_becomes_a_link(self):
        views = self._views()
        found = vb.link_charts(views, "/api/viertelstunden_waechter/vollbild", "KEY")
        self.assertEqual(len(found), 1)
        cid, tpl = next(iter(found.items()))
        self.assertEqual(tpl, CHART)   # the page renders the card as it was
        card = views[0]["sections"][0]["cards"][0]["content"]
        self.assertIn(f'<a href="/api/viertelstunden_waechter/vollbild/KEY/{cid}" target="_blank">![](data:image/svg+xml;utf8,', card)
        self.assertTrue(card.endswith("</a>{% endif %}"))

    def test_text_and_other_cards_stay(self):
        views = self._views()
        vb.link_charts(views, "/b", "K")
        self.assertEqual(views[0]["sections"][0]["cards"][1]["content"], "only text")
        self.assertEqual(views[0]["sections"][0]["cards"][2], {"type": "tile", "entity": "sensor.y"})

    def test_the_same_card_gets_the_same_id(self):
        a, b = vb.link_charts(self._views(), "/b", "K"), vb.link_charts(self._views(), "/b", "K")
        self.assertEqual(list(a), list(b))

    def test_every_chart_of_the_real_dashboard(self):
        ids = {k: f"{d}.guard_{k}" for k, d in dashboard.ENTITY_KEYS.items()}
        views = dashboard.build_views(ids, "de")
        before = sum(str(v).count("data:image/svg+xml") for v in views)
        found = vb.link_charts(views, "/api/viertelstunden_waechter/vollbild", "K")
        self.assertGreaterEqual(len(found), 4)
        text = str(views)
        self.assertEqual(text.count('target="_blank">![](data:image/svg+xml'), before)
        for tpl in found.values():
            self.assertIn("data:image/svg+xml", tpl)


class PageTests(unittest.TestCase):
    def test_extract_the_image(self):
        self.assertEqual(vb.extract_image("x ![](data:image/svg+xml;utf8,%3Csvg%3E) y"), "%3Csvg%3E")
        self.assertIsNone(vb.extract_image(""))
        self.assertIsNone(vb.extract_image("no chart"))

    def test_page_allows_zoom_and_shows_the_image(self):
        p = vb.page("Viertelstunden-Wächter", "%3Csvg%3E", "de")
        self.assertIn("user-scalable=yes", p)
        self.assertIn('<img src="data:image/svg+xml;utf8,%3Csvg%3E"', p)
        self.assertIn("zwei Fingern", p)
        self.assertNotIn("<script", p)

    def test_page_without_a_chart(self):
        self.assertIn("empty right now", vb.page("Viertelstunden-Wächter", None, "en"))

    def test_nothing_from_the_image_can_break_out(self):
        p = vb.page("<b>", '"><script>x</script>', "en")
        self.assertNotIn("<script>", p)
        self.assertNotIn("<b>", p)


if __name__ == "__main__":
    unittest.main()
