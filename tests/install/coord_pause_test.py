"""Wallbox may pause as the last measure (BETA, 0.16.0) in the coordinator: evcc mode off and back to the mode from before (also
after a restart), the pause and allow commands of another wallbox, a mode someone changed meanwhile stays, the message and the status.
The coordinator's own methods with a fake Home Assistant state machine and a fake evcc. Needs Home Assistant installed, so it runs in
its Docker image:

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/coord_pause_test.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import coordinator as co  # noqa: E402
from custom_components.viertelstunden_waechter.engine import STRATEGY_ORDER, Action, DeviceConfig, Guard  # noqa: E402
from custom_components.viertelstunden_waechter.evcc import parse_loadpoint  # noqa: E402
from custom_components.viertelstunden_waechter.messages import Messages  # noqa: E402

T0 = datetime(2026, 11, 27, 18, 0)
PAUSE, GO = "switch.wallbox_laden", "button.wallbox_start"


def evcc_state(mode: str = "pv", charging: bool = True) -> dict:
    return {"loadpoints": [{"title": "eGolf", "mode": mode, "connected": True, "charging": charging,
                            "chargePower": 4140 if charging else 0, "maxCurrent": 6, "minCurrent": 6, "offeredCurrent": 6,
                            "phasesActive": 3, "phasesConfigured": 3, "chargerPhases1p3p": False}]}


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def set_mode(self, lp, mode):
        self.calls.append(("mode", lp, mode))

    async def set_max_current(self, lp, amps):
        self.calls.append(("maxcurrent", lp, amps))

    async def set_phases(self, lp, phases):
        self.calls.append(("phases", lp, phases))


def make(may_pause: bool = True, kind: str = "evcc"):
    w = object.__new__(co.Waechter)
    w.t = Messages("de")
    if kind == "evcc":
        dev = {"id": "egolf", "kind": "evcc", "name": "eGolf", "priority": 1, "min_current": 6, "max_current": 16,
               "evcc_url": "http://evcc.local:7070", "evcc_loadpoint": 1, "evcc_one_phase": False}
    else:
        dev = {"id": "egolf", "kind": "wallbox", "name": "eGolf", "priority": 1, "min_current": 6, "max_current": 16,
               "power_entity": "sensor.wb_power", "current_entity": "number.wb_current",
               "pause_entity": PAUSE, "pause_value": "off", "resume_entity": GO}
    if may_pause:
        dev["may_pause"] = True
    w.raw_devices = {"egolf": dev}
    w._evcc_lp = {"egolf": parse_loadpoint(evcc_state(), 1)}
    w._evcc_orig = {}
    w._pw_seen = {}
    w.client = FakeClient()
    w._evcc_client = lambda url, pw: w.client
    w.states = {"sensor.wb_power": "4140", "number.wb_current": "6", PAUSE: "on"}
    w.hass = types.SimpleNamespace(states=types.SimpleNamespace(
        get=lambda eid: types.SimpleNamespace(state=w.states[eid], attributes={"unit_of_measurement": "W"} if eid == "sensor.wb_power" else {},
                                              last_changed=T0) if eid in w.states else None),
        config=types.SimpleNamespace(language="de"))
    w.lines, w.set_calls, w.notes = [], [], []

    async def set_entity(eid, value):
        w.set_calls.append((eid, value))
        if eid in w.states:
            w.states[eid] = value

    w._set_entity = set_entity
    w._log = lambda a, shadow: w.lines.append(a.text)
    w.guard = Guard([DeviceConfig.from_dict(w._engine_dict(d)) for d in w.raw_devices.values()], STRATEGY_ORDER, 230.0, "de")
    w.executing = True
    return w


def run(coro):
    return asyncio.run(coro)


def pause_cycle(w):
    """Drive the guard (house 8 kW + car 4.14 kW, target 9.5 kW) until it pauses, executing what it returns."""
    for i in range(12):
        acts = w.guard.step(T0 + timedelta(seconds=20 * i), 12.14, None, w._readings(), 10.0, 0.5, True)
        run(w._run(acts, True))
        if any(a.kind == "wb_pause" for a in acts):
            return acts
    raise AssertionError(w.lines)


class EvccPauseTests(unittest.TestCase):
    def test_mode_reaches_the_engine(self):
        w = make()
        r = w._readings()["egolf"]
        self.assertEqual((r.mode, r.paused), ("pv", False))
        w._evcc_lp["egolf"] = parse_loadpoint(evcc_state("off", False), 1)
        r = w._readings()["egolf"]
        self.assertEqual((r.mode, r.paused), ("off", True))

    def test_pause_is_mode_off_and_back_to_the_mode_from_before(self):
        w = make()
        pause_cycle(w)
        self.assertIn(("mode", 1, "off"), w.client.calls)
        self.assertEqual(w.guard.interventions["egolf"]["paused"]["mode"], "pv")
        w._evcc_lp["egolf"] = parse_loadpoint(evcc_state("off", False), 1)
        w.client.calls.clear()
        run(w._exec(Action("egolf", "wb_resume", "pv", "eGolf wieder erlaubt", False)))
        self.assertEqual(w.client.calls, [("mode", 1, "pv")])

    def test_after_a_restart_the_old_mode_comes_back(self):
        w = make()
        pause_cycle(w)
        stored = json.loads(json.dumps({"interventions": w.guard.interventions}))   # what the store of the entry keeps
        w2 = make()
        w2._evcc_lp["egolf"] = parse_loadpoint(evcc_state("off", False), 1)
        w2.guard.load(stored)
        run(w2._run(w2.guard.release_all(T0 + timedelta(minutes=10), w2._readings(), "Neustart"), True))
        self.assertIn(("mode", 1, "pv"), w2.client.calls)

    def test_a_mode_changed_meanwhile_stays(self):
        w = make()
        w._evcc_lp["egolf"] = parse_loadpoint(evcc_state("now"), 1)
        run(w._exec(Action("egolf", "wb_resume", "pv", "eGolf wieder erlaubt", False)))
        self.assertEqual(w.client.calls, [])
        self.assertTrue(any("eGolf" in ln for ln in w.lines), w.lines)

    def test_switch_off_nothing_is_sent_but_the_ceiling(self):
        w = make(may_pause=False)
        for i in range(30):
            run(w._run(w.guard.step(T0 + timedelta(seconds=20 * i), 12.14, None, w._readings(), 10.0, 0.5, True), True))
        self.assertFalse([c for c in w.client.calls if c[0] == "mode"], w.client.calls)

    def test_unknown_mode_from_before_sends_nothing(self):
        """Review 27.11.2026: "now" would let a solar-only car charge at full grid power; nothing is sent, a line says why."""
        w = make()
        w._evcc_lp["egolf"] = parse_loadpoint(evcc_state("off", False), 1)
        run(w._exec(Action("egolf", "wb_resume", None, "eGolf wieder erlaubt", False)))
        self.assertEqual(w.client.calls, [])
        self.assertTrue(any("Modus" in ln and "eGolf" in ln for ln in w.lines), w.lines)


class OtherWallboxTests(unittest.TestCase):
    def test_pause_and_allow_commands(self):
        w = make(kind="wallbox")
        r = w._readings()["egolf"]
        self.assertFalse(r.paused)
        pause_cycle(w)
        self.assertIn((PAUSE, "off"), w.set_calls)
        self.assertTrue(w._readings()["egolf"].paused)
        w.set_calls.clear()
        run(w._exec(Action("egolf", "wb_resume", None, "eGolf wieder erlaubt", False)))
        self.assertEqual(w.set_calls, [(GO, "")])

    def test_switched_on_by_someone_meanwhile_stays(self):
        w = make(kind="wallbox")
        w.states[PAUSE] = "on"
        run(w._exec(Action("egolf", "wb_resume", None, "eGolf wieder erlaubt", False)))
        self.assertEqual(w.set_calls, [])

    def test_without_commands_never_paused(self):
        w = make(kind="wallbox")
        for k in ("pause_entity", "pause_value", "resume_entity"):
            w.raw_devices["egolf"].pop(k)
        self.assertFalse(DeviceConfig.from_dict(w._engine_dict(w.raw_devices["egolf"])).may_pause)


class ShownTests(unittest.TestCase):
    def test_paused_names_for_the_status(self):
        w = make()
        self.assertEqual(w.paused_names(), [])
        pause_cycle(w)
        self.assertEqual(w.paused_names(), ["eGolf"])
        w.executing = False
        self.assertEqual(w.paused_names(), [], "observe mode never pauses for real")

    def test_message_at_the_pause_even_shortly_after_another_one(self):
        w = make()
        w.notify_intervention = True
        w._session = ["17:55 eGolf 16 A -> 6 A"]
        w._last_push = T0 - timedelta(minutes=5)
        w.cfg = {"notify_services": "notify.handy"}
        w.entry = types.SimpleNamespace(title="Wächter")
        sent = []

        async def call(domain, service, data):
            sent.append(data["message"])

        w._call = call
        w.guard.interventions["egolf"] = {"since": T0.isoformat(), "paused": {"since": T0.isoformat(), "mode": "pv"}}
        run(w._push_intervention([Action("egolf", "wb_pause", None, "eGolf pausiert (2.6 kW zu viel, Mindeststrom reicht nicht)")], T0))
        self.assertEqual(len(sent), 1, sent)
        self.assertIn("pausiert", sent[0])


if __name__ == "__main__":
    unittest.main()
