"""Tests for 0.13: house and wallbox apart, battery reserve window, CSV export, AI explainer texts."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
import explain
import export
import forecast

TZ = timezone(timedelta(hours=1))
MON18 = datetime(2026, 10, 26, 18, 0, tzinfo=TZ)


class CombineTests(unittest.TestCase):
    def test_house_plus_wallbox_sample_by_sample(self):
        house, wb = forecast.LoadModel(), forecast.LoadModel()
        for h, w in ((1.0, 0.0), (1.2, 11.0), (0.9, 11.0), (1.1, 0.0)):
            house.add(MON18, h)
            wb.add(MON18, w)
        total = forecast.combine(house, wb)
        self.assertEqual(total.slots[forecast.slot_of(MON18)], [1.0, 12.2, 11.9, 1.1])
        # with the car: the usual evening charging is a risk; without the car it is not
        self.assertTrue(forecast.risk_windows(total.horizon(MON18, 1), 9.5))
        self.assertFalse(forecast.risk_windows(house.horizon(MON18, 1), 9.5))

    def test_older_house_samples_without_wallbox_part_stay_totals(self):
        house, wb = forecast.LoadModel(), forecast.LoadModel()
        for v in (12.0, 11.5, 1.0):     # history import: totals, car included
            house.add(MON18, v)
        wb.add(MON18, 10.0)             # since the split: only the newest sample has a wallbox part
        house.add(MON18, 1.2)
        self.assertEqual(forecast.combine(house, wb).slots[forecast.slot_of(MON18)], [12.0, 11.5, 1.0, 11.2])

    def test_slots_only_in_one_model(self):
        house, wb = forecast.LoadModel(), forecast.LoadModel()
        wb.add(MON18, 5.0)
        self.assertEqual(forecast.combine(house, wb).slots[forecast.slot_of(MON18)], [5.0])


class ReserveWindowTests(unittest.TestCase):
    W = [{"start": MON18, "end": MON18 + timedelta(hours=2), "high_kw": 12.0, "typical_kw": 1.0}]

    def test_lead_time_running_and_after(self):
        self.assertIsNone(forecast.reserve_window(self.W, MON18 - timedelta(minutes=61), 60))
        self.assertIsNotNone(forecast.reserve_window(self.W, MON18 - timedelta(minutes=59), 60))
        self.assertIsNotNone(forecast.reserve_window(self.W, MON18 + timedelta(minutes=90), 60))
        self.assertIsNone(forecast.reserve_window(self.W, MON18 + timedelta(hours=2), 60))
        self.assertIsNone(forecast.reserve_window([], MON18, 60))


class ExportTests(unittest.TestCase):
    ROWS = [["2026-10-25T16:45+01:00", 8.857, 10.2, 7.1], ["2026-10-25T17:00+01:00", 2.0, 2.0, None], ["kaputt", 1]]

    def test_quarters_standard(self):
        text, n = export.quarters_csv(self.ROWS)
        lines = text.strip().split("\n")
        self.assertEqual(n, 2)
        self.assertEqual(lines[0], "start,end,import_kw,import_kwh,without_guard_kw,wallbox_kw")
        self.assertEqual(lines[1], "2026-10-25T16:45+01:00,2026-10-25T17:00+01:00,8.857,2.214,10.200,7.100")
        self.assertTrue(lines[2].endswith(",2.000,"))

    def test_quarters_excel_and_since(self):
        text, n = export.quarters_csv(self.ROWS, "excel_de", datetime(2026, 10, 25, 16, 50, tzinfo=TZ))
        self.assertEqual(n, 1)
        self.assertIn("2026-10-25T17:00+01:00;2026-10-25T17:15+01:00;2,000;0,500;2,000;", text)

    def test_days(self):
        text, n = export.days_csv({"2026-10-24": {"kw": 7.9, "at": "18:15"}, "2026-10-25": {"kw": 9.084}}, "excel_de", "2026-10-25")
        self.assertEqual((n, text.strip().split("\n")[1]), (1, "2026-10-25;9,084;"))


class ExplainTests(unittest.TestCase):
    def test_instructions_contain_the_data_and_the_rules(self):
        t = explain.build_instructions("de", "25.10.2026", ["16:45:03  Wallbox 16 A -> 12 A (3-phasig, 1.7 kW zu viel)"],
                                       10.0, 9.5, 9.08, "16:45", 6, 0, False)
        for part in ("Wallbox 16 A -> 12 A", "Grenze: 10.0 kW", "9.08 kW um 16:45", "Eingriffe: 6", "Erfinde nichts"):
            self.assertIn(part, t)
        self.assertNotIn("Beobachtungsmodus", t)
        self.assertIn("observe mode", explain.build_instructions("en", "x", [], 10, 9.5, None, None, 1, 0, True))

    def test_plain_summary_and_response(self):
        self.assertIn("9,1 kW", explain.plain_summary("de", 0, 9.08, 10.0))
        self.assertIn("10,0 kW", explain.plain_summary("de", 0, 9.08, 10.0))
        self.assertTrue(explain.plain_summary("de", 0, 9.08, 10.0, "27.10.").startswith("Am 27.10. musste"))
        self.assertIn("on 27.10.", explain.plain_summary("en", 0, 9.08, 10.0, "27.10."))
        self.assertEqual(explain.extract_text({"conversation_id": "x", "data": " Heute ... "}), "Heute ...")
        self.assertEqual(explain.extract_text({"data": {"text": "a"}}), "a")
        self.assertEqual(explain.extract_text(None), "")


if __name__ == "__main__":
    unittest.main()


class LanguageTests(unittest.TestCase):
    def test_log_lines_follow_the_language(self):
        import messages
        from sim import House, devices, engine, run

        for lang, word in (("de", "zu viel"), ("en", "too much"), ("fr", "too much")):
            house = House(cooker=[(5, 35, 7.0)])
            _, log = run(house, engine.Guard(devices(), lang=lang), 30)
            self.assertTrue(any(word in line for line in log), (lang, log[:3]))
        self.assertEqual(messages.language("de-AT"), "de")
        self.assertEqual(messages.language("en-GB"), "en")
        self.assertEqual(messages.language(None), "en")

    def test_both_languages_have_the_same_keys(self):
        import messages

        self.assertEqual(set(messages.MESSAGES["de"]), set(messages.MESSAGES["en"]))
