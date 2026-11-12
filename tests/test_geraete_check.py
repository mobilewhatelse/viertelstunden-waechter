"""Tests for the measuring part of the device check (the judgement is made by the check service and tested there)."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

import sim  # noqa: F401  (puts the integration folder on sys.path)
from geraete_check import ART_WATER_HEATER, DeviceCheck, Sample, text

TZ = timezone(timedelta(hours=1))
T0 = datetime(2027, 1, 4, 8, 0, tzinfo=TZ)
STEP = timedelta(seconds=20)


def charge(c: DeviceCheck, start: datetime, minutes: int, power_w: float, amps: float = 16, phases: int = 3,
           soc: float | None = 50, temp: float | None = 5.0, intervened: bool = False, max_a: float = 16) -> datetime:
    t = start
    for _ in range(int(minutes * 3)):
        c.step(t, {"wb": Sample("wallbox", power_w=power_w, current_a=amps, phases=phases, soc=soc, max_current=max_a,
                                intervened=intervened)}, temp)
        t += STEP
    for _ in range(60):
        c.step(t, {"wb": Sample("wallbox", power_w=0.0, current_a=amps, phases=phases, soc=soc, max_current=max_a)}, temp)
        t += STEP
    return t


def sessions(c: DeviceCheck) -> list:
    return c.dev["wb"]["wb"]["sessions"]


class WallboxTests(unittest.TestCase):
    def test_share_of_the_setting(self):
        c = DeviceCheck()
        charge(c, T0, 40, 7300)
        s = sessions(c)
        self.assertEqual(len(s), 1)
        self.assertAlmostEqual(s[0][1], 7300 / 11040, places=2)
        self.assertAlmostEqual(s[0][2], 7.3, places=1)   # at the highest setting: full power

    def test_throttled_setting_measured_against_setting(self):
        c = DeviceCheck()
        charge(c, T0, 40, 6 * 3 * 230 * 0.97, amps=6)
        s = sessions(c)
        self.assertAlmostEqual(s[0][1], 0.97, places=2)
        self.assertIsNone(s[0][2])                        # not the highest setting

    def test_not_measured_full_car_cold_intervention_short(self):
        c = DeviceCheck()
        t = charge(c, T0, 40, 4000, soc=92)
        t = charge(c, t, 40, 4000, temp=-5)
        t = charge(c, t, 40, 4000, intervened=True)
        charge(c, t, 8, 4000)
        self.assertEqual(sessions(c), [])

    def test_request_days_ago_without_date(self):
        c = DeviceCheck()
        charge(c, T0, 40, 7300)
        charge(c, T0 + timedelta(days=2), 40, 7300)
        r = c.request(T0 + timedelta(days=3), {}, "0.15.0")
        self.assertEqual([x[0] for x in r["geraete"][0]["ladungen"]], [3, 1])
        self.assertNotIn("2027", json.dumps(r))


def swing(c: DeviceCheck, t: datetime, soc_from: float, soc_to: float, kwh: float, minutes: int = 120) -> datetime:
    n = minutes * 3
    p = kwh / (minutes / 60) * 1000
    for i in range(n + 1):
        soc = soc_from + (soc_to - soc_from) * i / n
        c.step(t, {"bat": Sample("battery", soc=soc, battery_w=p if soc_to > soc_from else -p)}, 5.0)
        t += STEP
    return t


class BatteryTests(unittest.TestCase):
    def run_swings(self, n: int, cap: float = 1.5) -> DeviceCheck:
        c, t, soc, up = DeviceCheck(), T0, 10.0, True
        for _ in range(n):
            to = 90.0 if up else 10.0
            t = swing(c, t, soc, to, cap * 0.8)
            soc, up = to, not up
        swing(c, t, soc, 50.0 if soc > 50 else 40.0, 0.1, minutes=20)
        return c

    def test_capacity_per_swing(self):
        c = self.run_swings(4)
        b = c.dev["bat"]["bat"]
        self.assertEqual(len(b["base"]), 4)
        for cap, direction, span in b["base"]:
            self.assertAlmostEqual(cap, 1.5, places=1)
            self.assertIn(direction, (1, -1))
            self.assertGreaterEqual(span, 75)

    def test_base_kept_for_good(self):
        c = self.run_swings(60)
        b = c.dev["bat"]["bat"]
        self.assertEqual(len(b["base"]), 10)
        self.assertEqual(len(b["swings"]), 40)            # the newest only
        r = c.request(T0, {}, "x")["geraete"][0]
        self.assertEqual(len(r["grund"]), 10)

    def test_small_swings_ignored(self):
        c, t = DeviceCheck(), T0
        for i in range(10):
            t = swing(c, t, 40, 70, 0.3) if i % 2 == 0 else swing(c, t, 70, 40, 0.3)
        self.assertEqual(c.dev["bat"]["bat"]["base"], [])


def runs(c: DeviceCheck, t: datetime, n: int, power: float, minutes: int = 30) -> datetime:
    for _ in range(n):
        for _ in range(minutes * 3):
            c.step(t, {"pool": Sample("switch", power_w=power, is_on=True)}, 10.0)
            t += STEP
        for _ in range(30):
            c.step(t, {"pool": Sample("switch", power_w=0.0, is_on=False)}, 10.0)
            t += STEP
    return t


class SwitchTests(unittest.TestCase):
    def test_runs_and_quiet_time(self):
        c = DeviceCheck()
        t = runs(c, T0, 22, 635)
        self.assertEqual(c.dev["pool"]["sw"]["runs"], [635.0] * 22)
        for _ in range(int(2.1 * 3600 / 20)):
            c.step(t, {"pool": Sample("switch", power_w=2.0, is_on=True)}, 10.0)
            t += STEP
        g = c.request(t, {}, "x")["geraete"][0]
        self.assertGreaterEqual(g["an_ohne_strom_min"], 125)
        self.assertGreaterEqual(g["zog_wenn_an"], 0.99)   # from before the quiet spell
        runs(c, t, 1, 640)
        self.assertEqual(c.request(t, {}, "x")["geraete"][0]["an_ohne_strom_min"], 0)

    def test_switched_off_by_guard_is_not_quiet(self):
        c = DeviceCheck()
        t = runs(c, T0, 22, 635)
        for _ in range(400):
            c.step(t, {"pool": Sample("switch", power_w=0.0, is_on=True, intervened=True)}, 10.0)
            t += STEP
        self.assertEqual(c.request(t, {}, "x")["geraete"][0]["an_ohne_strom_min"], 0)


def days(c: DeviceCheck, start: datetime, values: list[tuple[float, float]], dev: str = "boiler") -> datetime:
    t = start
    for kwh, temp in values:
        p = kwh / 24 * 1000
        for _ in range(24 * 180):
            c.step(t, {dev: Sample("switch", art=ART_WATER_HEATER, power_w=p, is_on=True)}, temp)
            t += STEP
    c.step(t, {dev: Sample("switch", art=ART_WATER_HEATER, power_w=0.0, is_on=True)}, 0.0)
    return t


class DayAndPrivacyTests(unittest.TestCase):
    def test_day_rows(self):
        c = DeviceCheck()
        days(c, datetime(2027, 1, 1, tzinfo=TZ), [(3.0, 5.0), (4.0, 2.0)])
        g = c.request(datetime(2027, 1, 3, 1, tzinfo=TZ), {}, "x")["geraete"][0]
        self.assertEqual(len(g["tage"]), 2)
        self.assertAlmostEqual(g["tage"][0][0], 3.0, places=1)
        self.assertAlmostEqual(g["tage"][1][1], 2.0, places=1)

    def test_request_is_anonymous_and_new_days_go_once(self):
        c = DeviceCheck()
        days(c, datetime(2027, 1, 1, tzinfo=TZ), [(3.0, 5.0)] * 2, dev="mein-boiler-keller")
        now = datetime(2027, 1, 3, 1, tzinfo=TZ)
        r = c.request(now, {"mein-boiler-keller": {"hersteller": "X", "modell": "Y"}}, "0.15.0")
        raw = json.dumps(r)
        self.assertNotIn("2027", raw)
        self.assertNotIn("keller", raw)
        self.assertEqual([t["nr"] for t in r["neue_tage"]], [0, 0])
        self.assertEqual(r["geraete"][0]["hersteller"], "X")
        c.apply(now, {"geraete": [{"nr": 0, "status": "learning", "befunde": [], "lernt": [2, 20]}]})
        self.assertEqual(c.request(now, {}, "x")["neue_tage"], [])


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.c = DeviceCheck()
        charge(self.c, T0, 40, 7300)
        runs(self.c, T0 + timedelta(hours=3), 2, 600)
        self.c.request(T0 + timedelta(days=1), {}, "x")   # numbers: 0 = wb, 1 = pool

    def test_apply_maps_numbers_back(self):
        self.c.apply(T0, {"geraete": [
            {"nr": 0, "status": "warn", "befunde": [{"level": "warn", "key": "wb_phase", "werte": {"anteil_pct": 66, "band": "2/3", "ladungen": 3}}]},
            {"nr": 1, "status": "learning", "befunde": [], "lernt": [2, 20]}]})
        self.assertEqual(set(self.c.findings()), {"wb:wb_phase"})
        self.assertEqual(self.c.state(), "warn")
        self.assertEqual(self.c.result["pool"]["lernt"], [2, 20])

    def test_bad_answer_is_ignored(self):
        self.c.apply(T0, {"geraete": [{"nr": 7, "status": "warn"}, {"nr": "x"}, {"nr": 0, "status": "kaputt",
                                       "befunde": [{"level": "boese", "key": "x"}, "nein"]}]})
        self.assertEqual(self.c.findings(), {})
        self.assertEqual(self.c.result["wb"]["status"], "none")

    def test_states(self):
        self.assertEqual(self.c.state(), "none")
        self.c.apply(T0, {"geraete": [{"nr": 0, "status": "learning"}, {"nr": 1, "status": "learning"}]})
        self.assertEqual(self.c.state(), "learning")
        self.c.apply(T0, {"geraete": [{"nr": 0, "status": "ok"}, {"nr": 1, "status": "hint", "befunde": [{"level": "hint", "key": "sw_more"}]}]})
        self.assertEqual(self.c.state(), "hint")
        self.c.clear()
        self.assertEqual(self.c.state(), "none")

    def test_round_trip(self):
        self.c.apply(T0, {"geraete": [{"nr": 0, "status": "warn", "befunde": [{"level": "warn", "key": "wb_low", "werte": {}}]}]})
        c2 = DeviceCheck.from_dict(json.loads(json.dumps(self.c.to_dict())))
        self.assertEqual(set(c2.findings()), {"wb:wb_low"})
        self.assertEqual(c2.measured()["wb"]["charges"], 1)

    def test_forget_removed_device(self):
        self.c.forget({"wb"})
        self.assertEqual(set(self.c.dev), {"wb"})


class TextTests(unittest.TestCase):
    def test_texts(self):
        de = text("de-AT", "wb_phase", "Wallbox", {"anteil_pct": 66, "band": "2/3", "ladungen": 3})
        self.assertIn("66 %", de)
        self.assertIn("Phase", de)
        en = text("en", "bat_low", "Battery", {"jetzt_kwh": 1.2, "grund_kwh": 1.5, "pct": 80})
        self.assertIn("1.2 kWh", en)
        self.assertIn("?", text("de", "sw_more", "Pumpe", {}))          # missing values never break
        self.assertTrue(text("de", "neu_im_server", "X", {}).startswith("X"))


if __name__ == "__main__":
    unittest.main()
