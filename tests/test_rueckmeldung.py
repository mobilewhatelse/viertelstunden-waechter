"""Tests for the monthly id, the switch-over delete and the 'running since' class of the voluntary statistics."""

from __future__ import annotations

import asyncio  # noqa: F401 - load before the path change: the integration has its own select.py
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"))

import rueckmeldung as rm  # noqa: E402

UTC = timezone.utc


def at(y, m, d=15):
    return datetime(y, m, d, 12, 0, tzinfo=UTC)


class MonthlyIdTest(unittest.TestCase):
    def test_same_id_within_a_month(self):
        u = {}
        a = rm.kennung_fuer(u, at(2026, 11, 1))
        b = rm.kennung_fuer(u, at(2026, 11, 30))
        self.assertEqual(a, b)
        self.assertEqual(len(u["kennungen"]), 1)

    def test_new_id_each_month_and_three_kept(self):
        # the service keeps an id up to 60 days after its last report: the one from two months back must still be deletable
        u = {}
        ids = [rm.kennung_fuer(u, at(2026, m)) for m in (8, 9, 10, 11)]
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual([k["k"] for k in u["kennungen"]], ids[-3:])

    def test_failed_delete_waits_before_the_next_try(self):
        u = {}
        self.assertTrue(rm.loeschen_faellig(u, at(2026, 11, 1)))
        self.assertFalse(rm.loeschen_faellig(u, at(2026, 11, 1) + rm.ABSTAND_LOESCHEN / 2))
        self.assertTrue(rm.loeschen_faellig(u, at(2026, 11, 1) + rm.ABSTAND_LOESCHEN))
        u["kennungen"] = [{"k": "a", "monat": "2026-11"}]
        rm.geloescht(u, "a")
        self.assertNotIn("loeschversuch", u)

    def test_switch_over_deletes_the_old_fixed_id_first_even_while_sharing(self):
        u = {"kennung": "alt", "gesendet": "2026-11-10T10:00:00+00:00"}
        self.assertEqual(rm.zu_loeschen(u, True), "alt")
        rm.geloescht(u, "alt")
        self.assertNotIn("kennung", u)
        self.assertIsNone(rm.zu_loeschen(u, True))
        self.assertNotIn("gesendet", u)   # nothing left: the next weekly report goes out at once with the monthly id

    def test_switched_off_deletes_every_remembered_id(self):
        u = {}
        a = rm.kennung_fuer(u, at(2026, 10))
        b = rm.kennung_fuer(u, at(2026, 11))
        u["gesendet"] = "2026-11-15T12:00:00+00:00"
        self.assertIsNone(rm.zu_loeschen(u, True))
        gone = []
        while (k := rm.zu_loeschen(u, False)) is not None:
            gone.append(k)
            rm.geloescht(u, k)
        self.assertEqual(gone, [a, b])
        self.assertEqual(u, {})

    def test_broken_entries_are_ignored(self):
        u = {"kennungen": [{"k": ""}, "x", {"k": "a", "monat": "2026-11"}]}
        self.assertEqual(rm.kennung_fuer(u, at(2026, 11)), "a")
        self.assertEqual(len(u["kennungen"]), 1)


class RunningSinceTest(unittest.TestCase):
    def test_classes(self):
        seit = at(2026, 1, 1).isoformat()
        self.assertEqual(rm.laeuft_seit(seit, at(2026, 1, 20)), "0-1")
        self.assertEqual(rm.laeuft_seit(seit, at(2026, 3, 1)), "1-3")
        self.assertEqual(rm.laeuft_seit(seit, at(2026, 5, 1)), "3-6")
        self.assertEqual(rm.laeuft_seit(seit, at(2026, 9, 1)), ">6")

    def test_unknown_or_broken(self):
        self.assertIsNone(rm.laeuft_seit(None, at(2026, 1)))
        self.assertIsNone(rm.laeuft_seit("kein datum", at(2026, 1)))
        self.assertEqual(rm.laeuft_seit("2026-01-01T00:00:00", at(2026, 1, 2)), "0-1")   # naive date from an old store


class PayloadTest(unittest.TestCase):
    def test_new_fields_only_when_given(self):
        d = rm.statistik("viertelstunden_waechter", "1", "2026.11", "k", "at", "de", {})
        self.assertNotIn("laeuft_seit", d)
        self.assertNotIn("zusatz", d)
        self.assertEqual(d["schema"], 1)
        d = rm.statistik("viertelstunden_waechter", "1", "2026.11", "k", "at", "de", {}, "1-3", {"sonne_kwh_monat": "50-150"})
        self.assertEqual(d["laeuft_seit"], "1-3")
        self.assertEqual(d["zusatz"], {"sonne_kwh_monat": "50-150"})
        self.assertEqual(d["land"], "AT")


class SharedFileTest(unittest.TestCase):
    """rueckmeldung.py is the same file in the guard and in Plugwhen (0.15.1): the functions of both, with the same names."""

    def test_functions_of_both_integrations(self):
        public = {n for n in dir(rm) if callable(getattr(rm, n)) and not n.startswith("_") and getattr(rm, n).__module__ == rm.__name__}
        self.assertEqual(public, {
            "privacy_url", "katalog_fassung", "katalog", "katalog_fehlt", "zustimmung_merken", "neue_kennung", "monat", "kennung_fuer",
            "zu_loeschen", "geloescht", "loeschen_faellig", "laeuft_seit", "faellig", "herkunft", "statistik", "loeschen",
            "rueckmeldung", "senden"})

    def test_catalogue_version_from_several_sources(self):
        """Plugwhen asks entry options and store together; the guard asks one source (katalog), both give the same."""
        self.assertEqual(rm.katalog_fassung({}, None), 0)
        self.assertEqual(rm.katalog_fassung({"katalog": "x"}, {"katalog": None}), 0)
        self.assertEqual(rm.katalog_fassung({"katalog": 1}, {}), 1)
        self.assertEqual(rm.katalog_fassung({"katalog": -3}), 0)
        self.assertEqual(rm.katalog_fassung("kein dict", {"katalog": 1}), 1)   # unreadable source is skipped
        for usage in ({}, None, {"katalog": 1}, {"katalog": "2"}, {"katalog": "x"}, {"katalog": None}, {"katalog": -1}, {"check_ok": True}):
            self.assertEqual(rm.katalog(usage), rm.katalog_fassung(usage), usage)

    def test_catalogue_missing(self):
        self.assertFalse(rm.katalog_fehlt(False, {}))
        self.assertTrue(rm.katalog_fehlt(True, {}, {}))
        self.assertFalse(rm.katalog_fehlt(True, {}, {"katalog": rm.KATALOG}))
        usage: dict = {}
        rm.zustimmung_merken(usage)
        self.assertFalse(rm.katalog_fehlt(True, usage))
        self.assertEqual(usage, {"check_ok": True, "katalog": rm.KATALOG})

    def test_privacy_url_same_for_both_spellings(self):
        for lang, want in (("de", "de"), ("de-AT", "de"), ("DE_ch", "de"), ("en", "en"), ("fr", "en"), (None, "en"), ("", "en"), ("d", "en")):
            self.assertEqual(rm.privacy_url(lang), f"https://www.aiwhatelse.eu/datenschutz/?lang={want}#daten-teilen", lang)


if __name__ == "__main__":
    unittest.main()
