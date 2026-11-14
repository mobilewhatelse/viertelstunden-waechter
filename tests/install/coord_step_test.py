"""The minimum SOC follows the state of charge back up after a battery release (0.15) - the coordinator's own methods
with a fake Home Assistant state machine. Needs Home Assistant installed, so it runs in its Docker image:

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/coord_step_test.py
"""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import coordinator as co  # noqa: E402
from custom_components.viertelstunden_waechter.engine import Action  # noqa: E402
from custom_components.viertelstunden_waechter.messages import Messages  # noqa: E402

from datetime import datetime

MIN = "number.victron_minimum_soc"
CUR = "number.ess_max_charge_current"
NOON = datetime(2026, 11, 14, 12, 0)
NIGHT = datetime(2026, 11, 14, 22, 5)
SOC = "sensor.victron_soc"


class FakeGuard:
    def __init__(self) -> None:
        self.interventions: dict = {}


def make(stepwise: bool = True, soc: float = 20.0, minimum: str = "15", attrs: dict | None = None):
    w = object.__new__(co.Waechter)
    w.t = Messages("de")
    w.guard = FakeGuard()
    w._ratchet, w._battery_orig, w.lines, w.calls = {}, {}, [], []
    w.raw_devices = {"bat": {"kind": "battery", "name": "Victron", "soc_entity": SOC, "release_entity_1": MIN,
                             "release_value_1": "15", "restore_original": True, "restore_stepwise": stepwise}}
    w.states = {SOC: str(soc), MIN: minimum, CUR: "100"}
    a = {"min": 10, "max": 100, "step": 1} if attrs is None else attrs

    def state(eid):
        if eid not in w.states:
            return None
        return types.SimpleNamespace(state=w.states[eid], attributes=a if eid == MIN else {})

    async def set_entity(eid, value):
        w.calls.append((eid, value))
        w.states[eid] = value

    w._state = state
    w._set_entity = set_entity
    w._log = lambda act, shadow: w.lines.append(act.text)
    return w


def run(coro):
    return asyncio.run(coro)


class StepBackTests(unittest.TestCase):
    def test_follows_the_charge_up_to_the_old_value(self):
        w = make(soc=20.4)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        self.assertEqual(w.states[MIN], "20")                  # not 30 at once
        self.assertIn("folgt dem Ladestand", w.lines[-1])
        for soc, want in ((20.9, "20"), (21.0, "21"), (25.6, "25"), (24.0, "25"), (29.99, "29")):
            w.states[SOC] = str(soc)
            run(w._battery_step(NOON, True))
            self.assertEqual(w.states[MIN], want, soc)        # never down again
        w.states[SOC] = "31"
        run(w._battery_step(NOON, True))
        self.assertEqual(w.states[MIN], "30")
        self.assertEqual(w._ratchet, {})
        self.assertIn("wieder 30 %", w.lines[-1])

    def test_below_the_release_value_it_stays_there(self):
        w = make(soc=12.0)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        self.assertEqual((w.states[MIN], w.calls), ("15", []))
        self.assertEqual(w._ratchet["bat"]["last"], "15")
        w.states[SOC] = "16.2"
        run(w._battery_step(NOON, True))
        self.assertEqual(w.states[MIN], "16")

    def test_charged_enough_or_switched_off_goes_back_at_once(self):
        for kw in ({"soc": 35.0}, {"stepwise": False}):
            w = make(**kw)
            w._battery_orig["bat"] = {MIN: "30"}
            run(w._battery_restore("bat", w.raw_devices["bat"]))
            self.assertEqual((w.states[MIN], w._ratchet), ("30", {}), kw)

    def test_no_state_of_charge_goes_back_at_once(self):
        w = make()
        del w.states[SOC]
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        self.assertEqual(w.states[MIN], "30")

    def test_not_a_percent_value_goes_back_at_once(self):
        w = make()
        w.states[MIN] = "15"
        w._battery_orig["bat"] = {MIN: "800"}                  # e.g. an output power in W
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        self.assertEqual(w.states[MIN], "800")

    def test_changed_by_someone_else_is_left_alone(self):
        w = make(soc=20.0)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        w.states[MIN] = "50"
        w.states[SOC] = "28"
        run(w._battery_step(NOON, True))
        self.assertEqual((w.states[MIN], w._ratchet), ("50", {}))
        self.assertIn("anders eingestellt", w.lines[-1])

    def test_observe_or_off_puts_the_old_value_back(self):
        w = make(soc=20.0)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        run(w._battery_step(NOON, False))
        self.assertEqual((w.states[MIN], w._ratchet), ("30", {}))

    def test_released_again_keeps_the_old_value_as_original(self):
        w = make(soc=22.0)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        self.assertEqual(w.states[MIN], "22")
        run(release(w))
        self.assertEqual(w._battery_orig["bat"], {MIN: "30"})
        self.assertEqual((w.states[MIN], w._ratchet), ("15", {}))

    def test_while_released_nothing_moves(self):
        w = make(soc=20.0)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        w.guard.interventions["bat"] = object()
        w.states[SOC] = "27"
        run(w._battery_step(NOON, True))
        self.assertEqual(w.states[MIN], "20")

    def test_step_of_five(self):
        w = make(soc=23.0, attrs={"min": 10, "max": 100, "step": 5})
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        self.assertEqual(w.states[MIN], "20")
        w.states[SOC] = "26"
        run(w._battery_step(NOON, True))
        self.assertEqual(w.states[MIN], "25")

    def test_unload_puts_the_old_value_back(self):
        w = make(soc=20.0)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        run(w._step_finish("bat", "Integration beendet"))
        self.assertEqual((w.states[MIN], w._ratchet), ("30", {}))

    def test_device_deleted_leaves_the_setting(self):
        w = make(soc=20.0)
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        w.raw_devices = {}
        run(w._battery_step(NOON, True))
        self.assertEqual((w.states[MIN], w._ratchet), ("20", {}))


class RechargeTests(unittest.TestCase):
    def setUp(self):
        self.w = make(soc=20.0)
        self.w.raw_devices["bat"].update({"recharge_at": "22:00:00", "recharge_entity": CUR, "recharge_value": "40"})
        self.w._battery_orig["bat"] = {MIN: "30"}
        run(self.w._battery_restore("bat", self.w.raw_devices["bat"]))

    def test_before_the_time_it_only_follows(self):
        self.w.states[SOC] = "23"
        run(self.w._battery_step(NOON, True))
        self.assertEqual((self.w.states[MIN], self.w.states[CUR]), ("23", "100"))

    def test_from_the_time_slowly_to_the_old_value_then_current_back(self):
        w = self.w
        run(w._battery_step(NIGHT, True))
        self.assertEqual((w.states[CUR], w.states[MIN]), ("40", "30"))
        self.assertEqual(w.calls[-2:], [(CUR, "40"), (MIN, "30")])      # the slow current first
        self.assertIn("Nachladezeit", w.lines[-1])
        w.states[SOC] = "27"
        run(w._battery_step(NIGHT, True))
        self.assertEqual((w.states[CUR], w.states[MIN]), ("40", "30"))
        w.states[SOC] = "30"
        run(w._battery_step(NOON, True))                                  # carries on past the 12 hours until reached
        self.assertEqual((w.states[CUR], w.states[MIN], w._ratchet), ("100", "30", {}))
        self.assertIn("wieder 30 %", w.lines[-1])

    def test_current_changed_meanwhile_stays(self):
        w = self.w
        run(w._battery_step(NIGHT, True))
        w.states[CUR] = "60"
        w.states[SOC] = "31"
        run(w._battery_step(NIGHT, True))
        self.assertEqual((w.states[CUR], w._ratchet), ("60", {}))

    def test_released_while_recharging_gives_the_current_back(self):
        w = self.w
        run(w._battery_step(NIGHT, True))
        run(release(w))
        self.assertEqual((w.states[CUR], w.states[MIN], w._battery_orig["bat"]), ("100", "15", {MIN: "30"}))

    def test_unload_or_observe_gives_both_back(self):
        for how in ("unload", "observe"):
            self.setUp()
            w = self.w
            run(w._battery_step(NIGHT, True))
            if how == "unload":
                run(w._step_finish("bat", "x"))
            else:
                run(w._battery_step(NIGHT, False))
            self.assertEqual((w.states[CUR], w.states[MIN], w._ratchet), ("100", "30", {}), how)

    def test_without_a_setting_only_the_minimum(self):
        w = make(soc=20.0)
        w.raw_devices["bat"]["recharge_at"] = "22:00"
        w._battery_orig["bat"] = {MIN: "30"}
        run(w._battery_restore("bat", w.raw_devices["bat"]))
        run(w._battery_step(NIGHT, True))
        self.assertEqual((w.states[MIN], w.states[CUR]), ("30", "100"))


async def release(w):
    """The battery_release branch of the coordinator, with the same fake."""
    await w._exec(Action("bat", "battery_release", None, "x", True))


if __name__ == "__main__":
    unittest.main()
