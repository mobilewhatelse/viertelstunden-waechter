"""0.16.0: *Message on intervention* is on, but no notify service is entered (user case: the user waited for messages that could not
come). A quiet hint at the status sensor and in the dashboard, no Repairs entry and no message: the switch is on by default, so a
Repairs entry would stay for everybody who does not use messages. It goes away by itself when a service is entered or the switch is
switched off."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import sim  # noqa: F401  (puts the integration folder on sys.path)
from dashboard import ENTITY_KEYS, build_views
from messages import notify_hint, notify_targets

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
IDS = {k: f"{d}.guard_{k}" for k, d in ENTITY_KEYS.items()}


class NotifyHintTests(unittest.TestCase):
    def test_switch_on_and_no_service_gives_a_hint(self):
        for raw in (None, "", "  ", ","):
            self.assertIsNotNone(notify_hint("de", True, raw), raw)
        self.assertIn("Benachrichtigungsdienst", notify_hint("de", True, ""))
        self.assertIn("notify service", notify_hint("en", True, None))

    def test_service_entered_no_hint(self):
        self.assertIsNone(notify_hint("de", True, "notify.mobile_app_handy"))
        self.assertIsNone(notify_hint("en", True, "notify.a, notify.b"))

    def test_switch_off_no_hint(self):
        self.assertIsNone(notify_hint("de", False, ""))
        self.assertIsNone(notify_hint("de", False, None))

    def test_an_entry_without_a_dot_is_no_service(self):
        """The same rule as when sending: only 'domain.service' is called, so 'handy' alone would send nothing."""
        self.assertEqual(notify_targets("handy"), [])
        self.assertIsNotNone(notify_hint("de", True, "handy"))
        self.assertEqual(notify_targets(" notify.a ,x, notify.b"), ["notify.a", "notify.b"])

    def test_coordinator_sends_with_the_same_rule(self):
        src = (PKG / "coordinator.py").read_text(encoding="utf-8")
        self.assertIn("notify_targets(self.cfg.get(CONF_NOTIFY))", src)


class DashboardTests(unittest.TestCase):
    def _md(self, lang: str) -> str:
        main = build_views(IDS, lang)[0]
        return next(c["content"] for s in main["sections"] for c in s["cards"]
                    if c.get("type") == "markdown" and "notify_hint" in c.get("content", ""))

    def test_hint_shown_only_when_there(self):
        try:
            import jinja2
        except ImportError:
            self.skipTest("jinja2 not installed")

        md = self._md("de")
        env = jinja2.Environment()
        render = lambda attrs: env.from_string(md).render(state_attr=lambda e, a: attrs.get(a))  # noqa: E731
        self.assertIn("kein Dienst", render({"effective_limit_kw": 4.0, "notify_hint": "kein Dienst"}))
        self.assertNotIn("⚠", render({"effective_limit_kw": 4.0, "notify_hint": None}))
        self.assertIn("⚠", render({"notify_hint": "kein Dienst"}))   # also without the limit attribute
        self.assertNotIn("None", render({}))


class TranslationTests(unittest.TestCase):
    def test_attribute_name_in_all_files(self):
        for f in ("strings.json", "translations/de.json", "translations/en.json"):
            d = json.loads((PKG / f).read_text(encoding="utf-8"))
            self.assertIn("name", d["entity"]["sensor"]["status"]["state_attributes"]["notify_hint"], f)


if __name__ == "__main__":
    unittest.main()
