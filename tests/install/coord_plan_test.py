"""Carrying out the charge plan when the pause or resume command fails (0.15): a readable error text and no new try every
cycle. The coordinator's own methods with a fake Home Assistant. Needs Home Assistant installed, so it runs in its Docker image:

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/coord_plan_test.py
"""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import coordinator as co  # noqa: E402
from custom_components.viertelstunden_waechter.messages import Messages  # noqa: E402

T0 = datetime(2026, 11, 15, 1, 12, 9)
CYCLE = timedelta(seconds=20)


def make(lang: str = "de"):
    w = object.__new__(co.Waechter)
    w.t = Messages(lang)
    w.plan_execute, w.plan_enabled, w.plan = True, True, {"status": "planned"}
    w._plan_paused, w._plan_cmd_at, w._plan_retry_at = False, None, None
    w.lines, w.calls, w.fail, w.want = [], [], None, False
    w._vehicle = lambda: {"stop_entity": "switch.wallbox", "stop_value": "off",
                          "start_entity": "switch.wallbox", "start_value": "on"}

    async def set_entity(eid, value):
        w.calls.append((eid, value))
        if w.fail is not None:
            raise w.fail

    w._set_entity = set_entity
    w._log = lambda act, shadow: w.lines.append(act.text)
    co.charging_allowed = lambda plan, now: w.want
    return w


def run(coro):
    return asyncio.run(coro)


class PlanCommandFailTests(unittest.TestCase):
    def test_a_failed_pause_is_not_sent_every_cycle(self):
        w = make()
        w.fail = TimeoutError()
        for i in range(6):                                     # two minutes of cycles
            run(w._execute_plan(T0 + i * CYCLE))
        self.assertEqual(len(w.calls), 1)
        self.assertEqual(len(w.lines), 1)
        self.assertFalse(w._plan_paused)
        w.fail = None
        run(w._execute_plan(T0 + timedelta(minutes=5)))       # tried again after five minutes, now it works
        self.assertEqual(len(w.calls), 2)
        self.assertTrue(w._plan_paused)
        self.assertIsNone(w._plan_retry_at)

    def test_the_text_says_what_went_wrong(self):
        w = make()
        w.fail = TimeoutError()
        run(w._execute_plan(T0))
        self.assertIn("keine Antwort innerhalb von 15 s", w.lines[-1])
        self.assertIn("neuer Versuch in 5 Min.", w.lines[-1])
        self.assertNotIn("()", w.lines[-1])
        e = make("en")
        e.fail = RuntimeError()                                # an error without a text: its type at least
        run(e._execute_plan(T0))
        self.assertIn("(RuntimeError)", e.lines[-1])
        self.assertIn("next try in 5 min", e.lines[-1])

    def test_a_failed_resume_is_tried_again_after_a_minute(self):
        w = make()
        w._plan_paused, w.want = True, True
        w.fail = TimeoutError()
        run(w._execute_plan(T0))
        run(w._execute_plan(T0 + 2 * CYCLE))
        self.assertEqual(len(w.calls), 1)
        self.assertIn("1 Min.", w.lines[-1])
        w.fail = None
        run(w._execute_plan(T0 + timedelta(minutes=1)))
        self.assertFalse(w._plan_paused)

    def test_plan_no_longer_needed_after_a_failed_pause_sends_nothing(self):
        w = make()
        w.fail = TimeoutError()
        run(w._execute_plan(T0))
        w.plan = {"status": "not_needed"}
        w.fail = None
        run(w._execute_plan(T0 + timedelta(minutes=6)))
        self.assertEqual(len(w.calls), 1)
        self.assertFalse(w._plan_paused)


def with_hass(w, delay: float, fail: Exception | None = None):
    """A fake Home Assistant whose service call needs `delay` seconds (a car or wallbox through its cloud)."""
    w.done = []

    async def service(domain, service, data, blocking=False):
        await asyncio.sleep(delay)
        if fail is not None:
            raise fail
        w.done.append((domain, service, data.get("entity_id")))

    w.hass = types.SimpleNamespace(
        async_create_task=lambda coro, name=None: asyncio.get_running_loop().create_task(coro),
        services=types.SimpleNamespace(async_call=service))
    return w


class SlowDeviceTests(unittest.TestCase):
    """0.14.3 cut a command off after 15 s - and Home Assistant then cancels it, so a slow device never got one."""

    def setUp(self):
        self._t = co.CALL_TIMEOUT_S
        co.CALL_TIMEOUT_S = 0.05

    def tearDown(self):
        co.CALL_TIMEOUT_S = self._t

    def test_a_slow_command_is_not_cancelled(self):
        w = with_hass(make(), 0.2)

        async def go():
            with self.assertRaises(co.SlowCall):
                await w._call("switch", "turn_on", {"entity_id": "switch.wallbox"})
            self.assertEqual(w.done, [])
            await asyncio.sleep(0.3)
        run(go())
        self.assertEqual(w.done, [("switch", "turn_on", "switch.wallbox")])   # arrived after all
        self.assertEqual(w.lines, [])                                          # and no error line

    def test_a_slow_command_that_fails_later_is_logged(self):
        w = with_hass(make(), 0.2, RuntimeError("cloud refused"))

        async def go():
            with self.assertRaises(co.SlowCall):
                await w._call("select", "select_option", {"entity_id": "select.max_ev_current"})
            await asyncio.sleep(0.3)
        run(go())
        self.assertIn("doch fehlgeschlagen (cloud refused)", w.lines[-1])

    def test_a_fast_error_comes_at_once(self):
        w = with_hass(make(), 0.0, RuntimeError("bad option"))
        with self.assertRaises(RuntimeError):
            run(w._call("select", "select_option", {"entity_id": "select.x"}))

    def test_charge_plan_counts_a_slow_command_as_sent(self):
        w = with_hass(make(), 0.2)
        w._set_entity = co.Waechter._set_entity.__get__(w)          # the real way: _set_entity -> _call

        async def go():
            await w._execute_plan(T0)
            await asyncio.sleep(0.3)
        run(go())
        self.assertTrue(w._plan_paused)
        self.assertIsNone(w._plan_retry_at)
        self.assertIn("Laden pausiert", w.lines[0])
        self.assertIn("antwortet langsam", w.lines[0])
        self.assertEqual(w.done, [("homeassistant", "turn_off", "switch.wallbox")])

    def test_guard_action_on_a_slow_wallbox_is_no_error(self):
        from custom_components.viertelstunden_waechter.engine import Action
        w = with_hass(make(), 0.2)
        w.raw_devices = {"wb": {"kind": "wallbox", "current_entity": "number.wb_current"}}

        async def go():
            await w._run([Action("wb", "set_current", 6, "Wallbox 16 A -> 6 A", True)], True)
            await asyncio.sleep(0.3)
        run(go())
        self.assertIn("antwortet langsam", w.lines[-1])
        self.assertFalse(any(l.startswith("Fehler") for l in w.lines))
        self.assertEqual(w.done, [("number", "set_value", "number.wb_current")])


if __name__ == "__main__":
    unittest.main()
