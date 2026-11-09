"""Tests for evcc as a wallbox of the guard: reading, the ceiling logic and the client (with a fake evcc)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

# other test files put the folder of the integration first on the path; it has files named select.py and number.py that would shadow the
# standard library when asyncio is imported for the first time, so take the folder off the path for that import
_shadow = [p for p in sys.path if p.replace("\\", "/").endswith("custom_components/viertelstunden_waechter")]
for _p in _shadow:
    sys.path.remove(_p)
import asyncio  # noqa: E402
sys.path[:0] = _shadow

# load the module from its file: the folder of the integration has files named select.py and number.py that must not shadow the standard library
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "evcc_under_test", Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter" / "evcc.py")
_evcc = importlib.util.module_from_spec(_spec)
sys.modules["evcc_under_test"] = _evcc
_spec.loader.exec_module(_evcc)
EvccAuthError, EvccClient, EvccError = _evcc.EvccAuthError, _evcc.EvccClient, _evcc.EvccError
normalize_url, parse_loadpoint, target_ceiling, virtual_current = _evcc.normalize_url, _evcc.parse_loadpoint, _evcc.target_ceiling, _evcc.virtual_current


def state(**lp):
    base = {"title": "Carport", "mode": "smart", "connected": True, "charging": True, "chargePower": 3680, "maxCurrent": 16, "minCurrent": 6,
            "offeredCurrent": 8, "phasesActive": 3, "phasesConfigured": 3, "chargerPhases1p3p": True}
    base.update(lp)
    return {"loadpoints": [base, {"title": "Garage", "maxCurrent": 10, "minCurrent": 6, "chargePower": 0}]}


class ParseTest(unittest.TestCase):
    def test_the_fields_of_a_loadpoint(self):
        lp = parse_loadpoint(state(), 1)
        self.assertEqual((lp["title"], lp["power_w"], lp["ceiling"], lp["min_current"], lp["offered"]), ("Carport", 3680.0, 16.0, 6.0, 8.0))
        self.assertEqual((lp["phases_active"], lp["phases_configured"], lp["phases_switchable"], lp["charging"]), (3, 3, True, True))

    def test_second_loadpoint_and_missing_ones(self):
        self.assertEqual(parse_loadpoint(state(), 2)["ceiling"], 10.0)
        for n in (0, 3, -1):
            self.assertIsNone(parse_loadpoint(state(), n))
        for bad in (None, {}, {"loadpoints": "x"}, {"loadpoints": [None]}):
            self.assertIsNone(parse_loadpoint(bad, 1))

    def test_missing_numbers_do_not_crash(self):
        lp = parse_loadpoint({"loadpoints": [{"title": "x"}]}, 1)
        self.assertIsNone(lp["ceiling"])
        self.assertIsNone(virtual_current(lp))


class VirtualCurrentTest(unittest.TestCase):
    def test_while_charging_it_is_what_evcc_offers(self):
        self.assertEqual(virtual_current(parse_loadpoint(state(), 1)), 8.0)       # ceiling 16 does nothing while evcc offers 8 A

    def test_never_above_the_ceiling(self):
        self.assertEqual(virtual_current(parse_loadpoint(state(offeredCurrent=20), 1)), 16.0)

    def test_not_charging_it_is_the_ceiling(self):
        for kw in (dict(charging=False), dict(offeredCurrent=0), dict(offeredCurrent=None)):
            self.assertEqual(virtual_current(parse_loadpoint(state(**kw), 1)), 16.0, kw)


class CeilingTest(unittest.TestCase):
    ORIG = {"ceiling": 16.0, "virtual": 8.0}

    def test_a_reduction_sets_that_value(self):
        self.assertEqual(target_ceiling(7.0, self.ORIG), (7, False))
        self.assertEqual(target_ceiling(6, None), (6, False))

    def test_giving_back_up_to_the_original_current_restores_the_original_ceiling(self):
        self.assertEqual(target_ceiling(8.0, self.ORIG), (16, True))              # the guard saw 8 A and wants "back to 8"
        self.assertEqual(target_ceiling(10.0, self.ORIG), (16, True))

    def test_a_step_up_below_the_original_keeps_the_lower_ceiling(self):
        self.assertEqual(target_ceiling(7.0, self.ORIG), (7, False))

    def test_the_whole_story(self):
        """evcc offers 8 A under a ceiling of 16 A. Reduce twice, give back stepwise, end at the original ceiling 16."""
        ceiling, orig = 16.0, None
        lp = parse_loadpoint(state(), 1)
        seen = virtual_current(lp)
        orig = {"ceiling": ceiling, "virtual": seen}
        for wish in (7.0, 6.0):
            ceiling = target_ceiling(wish, orig)[0]
        self.assertEqual(ceiling, 6)
        ceiling, restored = target_ceiling(7.0, orig)
        self.assertEqual((ceiling, restored), (7, False))
        ceiling, restored = target_ceiling(8.0, orig)
        self.assertEqual((ceiling, restored), (16, True))


class FakeResp:
    def __init__(self, status, body="", cookies=None, ctype="application/json"):
        self.status, self._body, self.cookies, self.content_type = status, body, cookies or {}, ctype

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeEvcc:
    """A session that behaves like evcc: optional password, a state, and it records what was set."""

    def __init__(self, password=None, state_json='{"loadpoints": [{"title": "A", "maxCurrent": 16, "minCurrent": 6}]}'):
        self.password, self.state_json, self.calls, self.logins = password, state_json, [], 0

    def request(self, method, url, headers=None, json=None, **kw):
        path = url.split("//", 1)[1].split("/", 1)[1]
        self.calls.append((method, "/" + path, (headers or {}).get("Cookie")))
        if path == "api/auth/login":
            self.logins += 1
            if json and json.get("password") == self.password:
                return FakeResp(200, "", cookies={"auth": SimpleNamespace(value="tok")})
            return FakeResp(401)
        if self.password and (headers or {}).get("Cookie") != "auth=tok":
            return FakeResp(401)
        if path == "api/state":
            return FakeResp(200, self.state_json)
        return FakeResp(200, "10")


def run(coro):
    return asyncio.run(coro)


class ClientTest(unittest.TestCase):
    def test_state_without_password(self):
        s = FakeEvcc()
        st = run(EvccClient(s, "192.168.1.5:7070").state())
        self.assertEqual(st["loadpoints"][0]["title"], "A")
        self.assertEqual(s.calls[0][:2], ("GET", "/api/state"))

    def test_url_is_completed(self):
        self.assertEqual(normalize_url(" 192.168.1.5:7070/ "), "http://192.168.1.5:7070")
        self.assertEqual(normalize_url("https://evcc.local"), "https://evcc.local")

    def test_set_ceiling_and_phases_use_the_documented_paths(self):
        s = FakeEvcc()
        c = EvccClient(s, "http://e:7070")
        run(c.set_max_current(2, 10))
        run(c.set_phases(1, 1))
        self.assertEqual([(m, p) for m, p, _ in s.calls], [("POST", "/api/loadpoints/2/maxcurrent/10"), ("POST", "/api/loadpoints/1/phases/1")])

    def test_with_a_password_it_logs_in_by_itself_and_keeps_the_cookie(self):
        s = FakeEvcc(password="geheim")
        c = EvccClient(s, "http://e:7070", "geheim")
        run(c.state())
        run(c.set_max_current(1, 8))
        self.assertEqual(s.logins, 1)                                              # one login for both calls
        self.assertEqual(s.calls[-1][2], "auth=tok")

    def test_it_logs_in_again_when_the_login_has_run_out(self):
        s = FakeEvcc(password="geheim")
        c = EvccClient(s, "http://e:7070", "geheim")
        run(c.state())
        c._cookie = "stale"
        run(c.state())
        self.assertEqual(s.logins, 2)

    def test_a_wrong_or_missing_password_is_an_auth_error(self):
        with self.assertRaises(EvccAuthError):
            run(EvccClient(FakeEvcc(password="geheim"), "http://e", "falsch").state())
        with self.assertRaises(EvccAuthError):
            run(EvccClient(FakeEvcc(password="geheim"), "http://e").state())

    def test_a_connection_problem_is_an_evcc_error(self):
        class Broken:
            def request(self, *a, **k):
                raise OSError("no route")
        with self.assertRaises(EvccError):
            run(EvccClient(Broken(), "http://e").state())

    def test_a_strange_answer_is_an_error(self):
        with self.assertRaises(EvccError):
            run(EvccClient(FakeEvcc(state_json="[1,2]"), "http://e").state())

    def test_older_versions_wrap_the_state_in_result(self):
        st = run(EvccClient(FakeEvcc(state_json='{"result": {"loadpoints": []}}'), "http://e").state())
        self.assertEqual(st, {"loadpoints": []})


choose_grid, sources_differ, parse_grid_kw = _evcc.choose_grid, _evcc.sources_differ, _evcc.parse_grid_kw


class GridSourceTest(unittest.TestCase):
    """Rule agreed 2026-11-09: the entered sensor wins, evcc fills gaps, differences are shown and never averaged."""

    def test_the_entered_sensor_wins(self):
        self.assertEqual(choose_grid(4.0, 6.0, True, True), (4.0, "sensor"))
        self.assertEqual(choose_grid(4.0, None, True, False), (4.0, "sensor"))

    def test_without_a_sensor_evcc_is_the_source(self):
        self.assertEqual(choose_grid(None, 6.0, False, False), (6.0, "evcc"))

    def test_reserve_takes_over_while_the_sensor_has_nothing_usable(self):
        self.assertEqual(choose_grid(None, 6.0, True, True), (6.0, "evcc"))

    def test_reserve_switched_off_means_no_data(self):
        self.assertEqual(choose_grid(None, 6.0, True, False), (None, None))

    def test_nothing_from_anyone_means_no_data(self):
        self.assertEqual(choose_grid(None, None, True, True), (None, None))
        self.assertEqual(choose_grid(None, None, False, True), (None, None))

    def test_never_an_average(self):
        for s, e in ((2.0, 8.0), (8.0, 2.0)):
            kw, _ = choose_grid(s, e, True, True)
            self.assertEqual(kw, s)

    def test_small_differences_are_normal(self):
        self.assertFalse(sources_differ(5.0, 5.2))       # 0.2 kW: below the absolute threshold
        self.assertFalse(sources_differ(10.0, 10.9))     # 0.9 kW but only 8 %
        self.assertFalse(sources_differ(None, 5.0))

    def test_clear_differences_are_found(self):
        self.assertTrue(sources_differ(5.0, 6.5))        # 1.5 kW and 23 %
        self.assertTrue(sources_differ(0.2, 1.0))

    def test_grid_power_from_the_state(self):
        self.assertAlmostEqual(parse_grid_kw({"grid": {"power": -3568.8}}), -3.5688)
        self.assertAlmostEqual(parse_grid_kw({"grid": {"power": 1200}}), 1.2)
        for st in (None, {}, {"grid": None}, {"grid": {"name": "grid"}}, {"grid": "x"}):
            self.assertIsNone(parse_grid_kw(st))


if __name__ == "__main__":
    unittest.main()
