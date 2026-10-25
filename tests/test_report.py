"""Tests for the weekly report."""

from __future__ import annotations

import unittest
from datetime import date

import sim  # noqa: F401  (puts the integration folder on sys.path)
from report import week_label, week_report


class ReportTests(unittest.TestCase):
    def test_full_week(self):
        peaks = {"2026-10-19": {"kw": 7.9, "at": "18:15"}, "2026-10-21": {"kw": 11.2, "at": "05:30"}, "2026-10-26": {"kw": 20.0}}
        counts = {"2026-10-21": {"real": 3, "shadow": 1, "miss": 1}, "2026-10-26": {"real": 9, "shadow": 0}}
        r = week_report(peaks, counts, 10.0, date(2026, 10, 19), month_peak_kw=11.75,
                        month_costs={"cost": 40.0, "saving": 12.5})
        self.assertEqual(r["week"], "2026-W43")
        self.assertEqual((r["peak_kw"], r["peak_day"], r["days_over"], r["days_with_data"]), (11.2, "2026-10-21", 1, 2))
        self.assertEqual((r["interventions"], r["observed"], r["unconfirmed"]), (3, 1, 1))
        for part in ("2026-W43", "19.10.–25.10.", "11.2 kW", "21.10. 05:30", "1 von 2", "Eingriffe: 3", "nicht umgesetzt", "11.8 kW", "12.50"):
            self.assertIn(part, r["text"])

    def test_empty_week_and_english(self):
        r = week_report({}, {}, 10.0, date(2026, 10, 19), lang="en")
        self.assertIn("No measurements", r["text"])
        self.assertIsNone(r["peak_kw"])

    def test_label(self):
        self.assertEqual(week_label(date(2027, 1, 4)), "2027-W01")


if __name__ == "__main__":
    unittest.main()
