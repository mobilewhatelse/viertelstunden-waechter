"""0.16.0: the coordinator's hint *Message on intervention on, but no notify service* (status attribute `notify_hint`). Needs Home
Assistant installed, so it runs in its Docker image:

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/coord_notify_test.py
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import coordinator as co  # noqa: E402
from custom_components.viertelstunden_waechter.engine import Action  # noqa: E402
from custom_components.viertelstunden_waechter.messages import Messages  # noqa: E402


def make(on: bool, services: str | None):
    w = object.__new__(co.Waechter)
    w.t = Messages("de")
    w.hass = type("H", (), {"config": type("C", (), {"language": "de"})()})()
    w.entry = type("E", (), {"title": "Wächter"})()
    w.notify_intervention = on
    w.cfg = {} if services is None else {"notify_services": services}
    w.calls, w.raw_devices = [], {}

    async def call(domain, service, data):
        w.calls.append(f"{domain}.{service}")

    w._call = call
    return w


class NotifyHintTests(unittest.TestCase):
    def test_on_without_service(self):
        self.assertIn("Benachrichtigungsdienst", make(True, None).notify_hint())
        self.assertIsNotNone(make(True, "").notify_hint())

    def test_service_set(self):
        self.assertIsNone(make(True, "notify.mobile_app_handy").notify_hint())

    def test_switch_off(self):
        self.assertIsNone(make(False, None).notify_hint())

    def test_sending_unchanged(self):
        w = make(True, "notify.a, x, notify.b")
        asyncio.run(w._exec(Action("", "notify", None, "Eingriff")))
        self.assertEqual(w.calls, ["notify.a", "notify.b"])


if __name__ == "__main__":
    unittest.main()
