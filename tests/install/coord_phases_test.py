"""Two-phase wallbox behind evcc (field case 26.11.2026, 0.16.0): evcc reports phasesActive 2, the coordinator's readings carry it
to the engine, and with the strategy "strict order" the wallbox (priority 1) is lowered before the battery (priority 3). The
coordinator's own methods with a fake Home Assistant state machine. Needs Home Assistant installed, so it runs in its Docker image:

docker run --rm -v "$PWD:/w" -w /w --entrypoint python ghcr.io/home-assistant/home-assistant:stable tests/install/coord_phases_test.py
"""

from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from custom_components.viertelstunden_waechter import coordinator as co  # noqa: E402
from custom_components.viertelstunden_waechter.engine import STRATEGY_ORDER, DeviceConfig, Guard  # noqa: E402
from custom_components.viertelstunden_waechter.evcc import parse_loadpoint  # noqa: E402

T0 = datetime(2026, 11, 26, 5, 30)
REL = "select.victron_ess_mode"
SOC = "sensor.victron_soc"


def evcc_state(phases_active: int) -> dict:
    return {"loadpoints": [{"title": "eGolf", "connected": True, "charging": True, "chargePower": 4400, "maxCurrent": 16,
                            "minCurrent": 6, "offeredCurrent": 9, "phasesActive": phases_active, "phasesConfigured": 3,
                            "chargerPhases1p3p": False}]}


def make(phases_active: int):
    w = object.__new__(co.Waechter)
    w.raw_devices = {
        "egolf": {"id": "egolf", "kind": "evcc", "name": "eGolf", "priority": 1, "min_current": 6, "max_current": 16,
                  "evcc_url": "http://evcc.local:7070", "evcc_loadpoint": 1, "evcc_one_phase": False},
        "speicher": {"id": "speicher", "kind": "battery", "name": "Speicher", "priority": 3, "power_w": 2000, "min_soc": 30,
                     "soc_entity": SOC, "release_entity_1": REL, "release_value_1": "Keep batteries charged"},
    }
    w._evcc_lp = {"egolf": parse_loadpoint(evcc_state(phases_active), 1)}
    w._pw_seen = {}
    states = {SOC: "80", REL: "Optimized"}
    w.hass = types.SimpleNamespace(states=types.SimpleNamespace(
        get=lambda eid: types.SimpleNamespace(state=states[eid], attributes={}, last_changed=T0) if eid in states else None))
    w.guard = Guard([DeviceConfig.from_dict(w._engine_dict(d)) for d in w.raw_devices.values()], STRATEGY_ORDER, 230.0, "de")
    return w


class TwoPhaseEvccTests(unittest.TestCase):
    def test_evcc_two_phases_reach_the_engine(self):
        w = make(2)
        r = w._readings()["egolf"]
        self.assertEqual((r.phases, r.current_a, r.power_w, r.available), (2, 9.0, 4400.0, True))
        self.assertEqual(w.guard._phases(w.guard.devices["egolf"], r), 2)

    def test_strict_order_lowers_the_two_phase_wallbox_before_the_battery(self):
        w = make(2)
        acts = w.guard.step(T0, 9.5 + 1.6, None, w._readings(), 10.0, 0.5, True)
        real = [a for a in acts if a.kind != "log"]
        self.assertEqual((real[0].device_id, real[0].kind, real[0].value), ("egolf", "set_current", 6), [a.text for a in acts])
        self.assertNotIn("speicher", w.guard.interventions)

    def test_three_phases_from_evcc_as_before(self):
        w = make(3)
        r = w._readings()["egolf"]
        self.assertEqual(w.guard._phases(w.guard.devices["egolf"], r), 3)


if __name__ == "__main__":
    unittest.main()
