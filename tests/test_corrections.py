"""Correcting a wrong quarter hour (seen on 2026-11-10: 10.8 kW recorded, the meter counted 8.4 kW)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"))

from corrections import correct_quarter, remove_quarter  # noqa: E402


def data():
    q = [["2026-11-01T00:00+01:00", 0.5, 0.5, None], ["2026-11-04T18:00+01:00", 9.482, 9.9, 8.6],
         ["2026-11-10T18:45+01:00", 9.379, 9.4, 8.5], ["2026-11-10T19:15+01:00", 10.808, 10.808, 8.0]]
    return q, {"2026-11-10": {"kw": 10.808, "at": "19:15"}}, {"2026-11": {"kw": 10.808, "ug": 10.808}}, \
        {"month": "2026-11", "kw": 10.808, "at": "2026-11-10T19:15+01:00"}


class CorrectTest(unittest.TestCase):
    def test_the_wrong_value_and_the_peaks(self):
        q, days, months, mp = data()
        r = correct_quarter(q, days, months, mp, "2026-11-10T19:15", 8.44)
        self.assertEqual((r["old_kw"], r["new_kw"]), (10.808, 8.44))
        self.assertEqual(q[3][1:3], [8.44, 8.44])
        self.assertEqual(days["2026-11-10"], {"kw": 9.379, "at": "18:45"})
        self.assertEqual(months["2026-11"]["kw"], 9.482)
        self.assertEqual(months["2026-11"]["ug"], 9.9)
        self.assertEqual((mp["kw"], mp["at"]), (9.482, "2026-11-04T18:00+01:00"))

    def test_an_older_real_peak_outside_the_record_stays(self):
        q, days, months, mp = data()
        q.pop(0)                                         # the record begins after the first of the month
        months["2026-11"] = {"kw": 11.5, "ug": 11.5}     # a real peak earlier in the month
        correct_quarter(q, days, months, mp, "2026-11-10T19:15", 8.44)
        self.assertEqual(months["2026-11"]["kw"], 11.5)

    def test_unknown_quarter(self):
        q, days, months, mp = data()
        with self.assertRaises(ValueError):
            correct_quarter(q, days, months, mp, "2026-11-10T20:00", 8.0)


class RemoveTest(unittest.TestCase):
    """Issue #4: a counter step after a gap was recorded as 20 kW; the real value is not known, so the quarter hour goes."""

    def test_the_quarter_hour_is_gone_and_the_peaks_are_the_next_highest(self):
        q, days, months, mp = data()
        r = remove_quarter(q, days, months, mp, "2026-11-10T19:15")
        self.assertTrue(r["removed"])
        self.assertEqual((r["old_kw"], r["new_kw"]), (10.808, None))
        self.assertEqual(len(q), 3)
        self.assertFalse([x for x in q if x[0].startswith("2026-11-10T19:15")])
        self.assertEqual(days["2026-11-10"], {"kw": 9.379, "at": "18:45"})
        self.assertEqual(months["2026-11"], {"kw": 9.482, "ug": 9.9})
        self.assertEqual((mp["kw"], mp["at"]), (9.482, "2026-11-04T18:00+01:00"))

    def test_the_only_quarter_hour_of_a_day(self):
        q, days, months, mp = data()
        days["2026-11-04"] = {"kw": 9.482, "at": "18:00"}
        remove_quarter(q, days, months, mp, "2026-11-04T18:00")
        self.assertNotIn("2026-11-04", days)
        self.assertEqual(months["2026-11"]["kw"], 10.808)   # the month's peak was another quarter hour: untouched

    def test_an_older_real_peak_outside_the_record_stays(self):
        q, days, months, mp = data()
        q.pop(0)
        months["2026-11"] = {"kw": 11.5, "ug": 11.5}
        remove_quarter(q, days, months, mp, "2026-11-10T19:15")
        self.assertEqual(months["2026-11"]["kw"], 11.5)

    def test_the_last_quarter_hour_of_the_record(self):
        q = [["2026-11-01T00:00+01:00", 20.2, 20.2, None]]
        days, months = {"2026-11-01": {"kw": 20.2, "at": "00:00"}}, {"2026-11": {"kw": 20.2, "ug": 20.2}}
        mp = {"month": "2026-11", "kw": 20.2, "at": "2026-11-01T00:00+01:00"}
        remove_quarter(q, days, months, mp, "2026-11-01T00:00")
        self.assertEqual((q, days), ([], {}))
        self.assertEqual(months["2026-11"], {"kw": 0.0, "ug": 0.0})
        self.assertEqual((mp["kw"], mp["at"]), (0.0, None))

    def test_unknown_quarter(self):
        q, days, months, mp = data()
        with self.assertRaises(ValueError):
            remove_quarter(q, days, months, mp, "2026-11-10T20:00")
        self.assertEqual(len(q), 4)


if __name__ == "__main__":
    unittest.main()
