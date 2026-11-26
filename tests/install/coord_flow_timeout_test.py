"""The set-up dialog does not hang when the recorder is slow (Raspberry Pi, big history, migration): the two looks into the recorder
(`_history_kw`: states of 3 days, `_peak_kw`: statistics of 10 days) give up after `HISTORY_TIMEOUT_S` and the hint is left out.
Needs Home Assistant installed, so it runs in its Docker image (see run_coordinator_tests.py)."""

from __future__ import annotations

import asyncio
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import config_flow as cf  # noqa: E402


class SlowRecorder:
    """The recorder instance whose database job takes much longer than the timeout."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    async def async_add_executor_job(self, func, *args):
        await asyncio.sleep(self.seconds)
        return func(*args) if self.seconds == 0 else {}


class SlowRecorderTest(unittest.TestCase):
    def run_slow(self, coro_func):
        hass = types.SimpleNamespace(states=types.SimpleNamespace(get=lambda e: None))
        with mock.patch("homeassistant.components.recorder.get_instance", lambda h: SlowRecorder(5.0)), \
                mock.patch.object(cf, "HISTORY_TIMEOUT_S", 0.2):
            t0 = time.monotonic()
            result = asyncio.run(coro_func(hass))
            return result, time.monotonic() - t0

    def test_history_gives_up(self):
        result, took = self.run_slow(lambda h: cf._history_kw(h, "sensor.grid", 3))
        self.assertEqual(result, [])
        self.assertLess(took, 2.0)

    def test_peak_gives_up(self):
        result, took = self.run_slow(lambda h: cf._peak_kw(h, "sensor.grid", False))
        self.assertIsNone(result)
        self.assertLess(took, 2.0)

    def test_a_fast_recorder_is_still_used(self):
        hass = types.SimpleNamespace(states=types.SimpleNamespace(get=lambda e: None))
        with mock.patch("homeassistant.components.recorder.get_instance", lambda h: SlowRecorder(0.0)):
            self.assertEqual(asyncio.run(cf._history_kw(hass, "sensor.grid", 3)), [])   # nothing recorded: empty, not an error


class CheapPathTest(unittest.TestCase):
    """A sensor that reports every 5 seconds: the statistics (five-minute means) are read, not the 17 000 states of a day."""

    def hass(self, unit="W"):
        st = types.SimpleNamespace(attributes={"unit_of_measurement": unit})
        return types.SimpleNamespace(states=types.SimpleNamespace(get=lambda e: st))

    def test_statistics_come_first_and_the_states_are_not_read(self):
        stats = {"sensor.grid": [{"start": 1763000000.0, "mean": 1500.0}, {"start": 1763000300.0, "mean": 1700.0}]}
        with mock.patch("homeassistant.components.recorder.get_instance", lambda h: SlowRecorder(0.0)),                 mock.patch("homeassistant.components.recorder.statistics.statistics_during_period", lambda *a: stats),                 mock.patch("homeassistant.components.recorder.history.state_changes_during_period",
                           side_effect=AssertionError("the states must not be read")):
            pts = asyncio.run(cf._history_kw(self.hass("W"), "sensor.grid", 3))
        self.assertEqual([round(v, 3) for _, v in pts], [1.5, 1.7])          # W -> kW

    def test_invert_turns_the_sign(self):
        stats = {"sensor.grid": [{"start": 1763000000.0, "mean": 1500.0}]}
        with mock.patch("homeassistant.components.recorder.get_instance", lambda h: SlowRecorder(0.0)),                 mock.patch("homeassistant.components.recorder.statistics.statistics_during_period", lambda *a: stats):
            pts = asyncio.run(cf._history_kw(self.hass("W"), "sensor.grid", 3, invert=True))
        self.assertEqual([round(v, 3) for _, v in pts], [-1.5])

    def test_without_statistics_the_states_are_read_without_attributes(self):
        calls = []

        def states(hass, start, end, entity_id, **kw):
            calls.append(kw)
            return {"sensor.grid": [types.SimpleNamespace(state="2000", last_changed=cf.dt_util.utcnow())]}

        with mock.patch("homeassistant.components.recorder.get_instance", lambda h: SlowRecorder(0.0)),                 mock.patch("homeassistant.components.recorder.statistics.statistics_during_period", lambda *a: {}),                 mock.patch("homeassistant.components.recorder.history.state_changes_during_period", states):
            pts = asyncio.run(cf._history_kw(self.hass("W"), "sensor.grid", 3))
        self.assertEqual([round(v, 3) for _, v in pts], [2.0])
        self.assertTrue(calls and calls[0].get("no_attributes") is True)


class SessionTest(unittest.TestCase):
    def test_the_own_session_is_detached_not_closed(self):
        """Home Assistant 2026.10+: a session made with auto_cleanup=False is released with detach(); close() logs a warning."""
        session = mock.Mock()
        session.close = mock.AsyncMock(side_effect=AssertionError("close() must not be called"))

        async def go():
            own = cf._OwnSession(types.SimpleNamespace())
            own._session = session
            await own.__aexit__(None, None, None)

        asyncio.run(go())
        session.detach.assert_called_once()


if __name__ == "__main__":
    unittest.main()
