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
        return {}


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


if __name__ == "__main__":
    unittest.main()
