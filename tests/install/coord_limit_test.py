"""0.16.0: the coordinator shows the effective limit at the status sensor (user case: limit 4 kW, month peak 9.7 kW). Needs Home
Assistant installed, so it runs in its Docker image:

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/coord_limit_test.py
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import coordinator as co  # noqa: E402
from custom_components.viertelstunden_waechter.messages import Messages  # noqa: E402

NOW = datetime(2026, 11, 27, 18, 0)


def make(limit: float = 4.0, peak: float | None = 9.7, paid: bool = True, lang: str = "de"):
    w = object.__new__(co.Waechter)
    w.t = Messages(lang)
    w.hass = type("H", (), {"config": type("C", (), {"language": lang})()})()
    w.limit_kw, w.paid_peak = limit, paid
    w.months = {"2026-11": {"kw": peak, "ug": peak}} if peak is not None else {}
    return w


class LimitInfoTests(unittest.TestCase):
    def test_user_case(self):
        w = make()
        self.assertEqual(w.effective_limit(NOW), 9.7)
        info = w.limit_info(NOW)
        self.assertEqual(info["limit_kw"], 4.0)
        self.assertEqual(info["effective_limit_kw"], 9.7)
        self.assertIn("9,7 kW", info["limit_note"])

    def test_switch_off(self):
        info = make(paid=False).limit_info(NOW)
        self.assertEqual(info["effective_limit_kw"], 4.0)
        self.assertIsNone(info["limit_note"])

    def test_peak_below_the_limit(self):
        info = make(limit=10.0, peak=7.0, lang="en").limit_info(NOW)
        self.assertEqual(info["effective_limit_kw"], 10.0)
        self.assertIsNone(info["limit_note"])

    def test_no_peak_yet(self):
        self.assertEqual(make(peak=None).effective_limit(NOW), 4.0)


if __name__ == "__main__":
    unittest.main()
