"""Bug report: nothing that identifies anybody, flat enough for the server (three levels), small enough (16 KB with the text)."""

from __future__ import annotations

import asyncio  # noqa: F401 - load before the path change: the integration has its own select.py
import json
import logging
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"))

import fehlerbericht as fb  # noqa: E402
import rueckmeldung as rm  # noqa: E402

NOW = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)


def depth(x, d=0):
    if isinstance(x, dict):
        return max([depth(v, d + 1) for v in x.values()] or [d])
    if isinstance(x, list):
        return max([depth(v, d + 1) for v in x] or [d])
    return d


class AnonymTests(unittest.TestCase):
    def test_nothing_that_identifies(self):
        t = fb.anonym("Wallbox Garage: number.garage_ladestrom antwortet nicht, http://192.168.5.10:8123/api von max@example.com,"
                      " Eintrag 01JABCDEF0123456789abcdef0 Seriennummer HM2A0B1C2D3E4F an 10.0.0.2", ["Wallbox Garage"])
        for bad in ("Garage", "garage_ladestrom", "192.168", "max@", "example.com", "HM2A0B1C2D3E4F", "10.0.0.2", "01JABCDEF"):
            self.assertNotIn(bad, t)
        self.assertIn("number antwortet nicht", t)

    def test_versions_stay(self):
        self.assertEqual(fb.anonym("Version 0.15.0 auf 2026.11.1"), "Version 0.15.0 auf 2026.11.1")


class CallsTests(unittest.TestCase):
    def test_slow_and_failed(self):
        c = fb.Calls()
        c.call("number.a", 2.0)
        c.call("number.a", 24.0)
        c.call("number.a", 1.0, TimeoutError())
        s = c.summary("number.a")
        self.assertEqual((s["befehle"], s["langsam"], s["fehlgeschlagen"], s["laengste_s"]), (3, 1, 1, 24.0))
        self.assertIn("1 langsam", c.text("number.a"))


class LinesTests(unittest.TestCase):
    def test_keeps_only_warnings_and_the_last_ones(self):
        h = fb.Lines()
        log = logging.getLogger("fb_test_w")
        log.addHandler(h)
        log.propagate = False
        try:
            log.info("not kept")
            for i in range(30):
                log.warning("Action %s failed", i)
        finally:
            log.removeHandler(h)
        self.assertEqual(len(h.lines), fb.MAX_LINES)
        self.assertEqual(h.lines[-1][2], "Action 29 failed")


class SensorTests(unittest.TestCase):
    def test_states(self):
        self.assertEqual(fb.sensor_state(None), "fehlt")
        self.assertEqual(fb.sensor_state(SimpleNamespace(state="unavailable")), "nicht_verfuegbar")
        self.assertEqual(fb.sensor_state(SimpleNamespace(state="5.2", last_reported=NOW - timedelta(minutes=1)), NOW), "ok")
        self.assertEqual(fb.rel_h((NOW - timedelta(hours=2)).isoformat(), NOW), "vor 2.0 h")


class ReportTests(unittest.TestCase):
    def report(self, lines=5):
        zustand = {"betriebsart": "active", "grenze_kw": 10.0, "werte": {"grid_kw": 9.8, "forecast_kw": 10.4}, "netz_zu_alt": False}
        geraete = [{"art": "wallbox", "eingriff_aktiv": True, "eingriff": {"from": 16, "to": 10},
                    "current_entity": "easee: Easee Home, ok 16 (6..32 Schritt 1), 3 Befehle, Mittel 1.2 s"},
                   {"art": "battery", "soc_entity": "victron: ok", "mindest_ladestand_folgt": {"target": 22, "last": 24}}]
        verlauf = [f"vor {i}.0 h: Wallbox Garage auf 10 A (number.garage_ladestrom)" for i in range(25)]
        zeilen = [("15. 19:44", "WARNING", f"Action set_current for Wallbox Garage failed: {'x' * 200}") for _ in range(lines)]
        return fb.bericht("0.15.0", "2026.11.1", {"geraete": {"wallbox": 1}, "herkunft": ["easee"]}, zustand, geraete, verlauf,
                          zeilen, {"evcc": None}, ["Wallbox Garage", "Familie Huber"])

    def test_flat_enough_for_the_server(self):
        self.assertLessEqual(depth(self.report()), 3)   # the server keeps three levels (gemeinsam.php sauber)

    def test_no_names_or_entity_ids(self):
        s = json.dumps(self.report(), ensure_ascii=False)
        for bad in ("Garage", "garage_ladestrom"):
            self.assertNotIn(bad, s)
        self.assertNotIn("evcc", self.report()["fehler"], "empty errors are left out")
        self.assertEqual(len(self.report()["verlauf"]), fb.MAX_LINES)

    def test_small_enough(self):
        b = self.report(lines=20)
        self.assertLessEqual(len(json.dumps(b, ensure_ascii=False).encode()), fb.MAX_BYTES)
        self.assertGreater(len(b["protokoll"]), 0)

    def test_display_after_sending(self):
        b = self.report()
        v = fb.anzeige(b, True, True)
        self.assertIn("ist angekommen", v)
        self.assertIn("Gerät 1: art: wallbox", v)
        self.assertIn("Verlauf:", v)
        self.assertIn("wäre genau das", fb.anzeige(b, True, False))
        self.assertIn("Exactly this was sent", fb.anzeige(b, False, True))

    def test_feedback_carries_it_only_on_request(self):
        self.assertNotIn("bericht", rm.rueckmeldung("viertelstunden_waechter", "0.15.0", "2026.11.1", "Hallo", None, None))
        d = rm.rueckmeldung("viertelstunden_waechter", "0.15.0", "2026.11.1", "Hallo", None, None, self.report())
        self.assertEqual(d["bericht"]["version"], "0.15.0")


class NoClockTests(unittest.TestCase):
    """Feedback 15.11.: the first real report carried the last press of a button and the departure time as clock times."""

    def test_masked_in_texts(self):
        t = fb.anonym("Abfahrt 07:20:00, gedrückt 2026-11-12T05:40:41.758274+00:00, Version 0.9.1 auf 2026.11.1")
        self.assertNotIn("07:20", t)
        self.assertNotIn("05:40", t)
        self.assertIn("0.9.1", t)
        self.assertIn("2026.11.1", t)

    def test_setting_now(self):
        self.assertEqual(fb.state_text("button.start", (NOW - timedelta(hours=3)).isoformat(), NOW), "gedrückt vor 3.0 h")
        self.assertEqual(fb.state_text("time.trip_time", "07:20:00", NOW), "gesetzt")
        self.assertEqual(fb.state_text("select.mode", "Eco", NOW), "Eco")
        self.assertEqual(fb.state_text("number.energy", "30000.0", NOW), "30000.0")

    def test_log_lines_relative(self):
        import time
        self.assertEqual(fb.ago(time.time() - 7200), "vor 2.0 h")


class GenericNameTests(unittest.TestCase):
    """Feedback 15.11.: devices called "Wallbox" and "Mercedes" erased the kind, the maker and an integration in the report."""

    def test_generic_words_are_no_names(self):
        keep = ["wallbox", "jackery", "Mercedes-Benz", "EQB 250"]
        self.assertEqual(fb.real_names(["Wallbox", "Mercedes", "Jackery", "Familie Huber", "", None], keep), ["Familie Huber"])

    def test_kind_and_maker_stay(self):
        t = fb.anonym("wallbox: mbapi2020, Mercedes-Benz, EQB 250", fb.real_names(["Wallbox", "Mercedes"], ["wallbox", "Mercedes-Benz"]))
        self.assertEqual(t, "wallbox: mbapi2020, Mercedes-Benz, EQB 250")


if __name__ == "__main__":
    unittest.main()
