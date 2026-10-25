"""Offline house model for the engine: car, cooker, pool pump, water heater, one grid meter.

Used by the tests and runnable on its own:  python tests/sim.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import datetime, timedelta, timezone

_PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "viertelstunden_waechter"
sys.path.insert(0, str(_PKG))  # pricing.py (and other pure modules) can be imported directly
_spec = importlib.util.spec_from_file_location("vw_engine", _PKG / "engine.py")
engine = importlib.util.module_from_spec(_spec)
sys.modules["vw_engine"] = engine
_spec.loader.exec_module(engine)

STEP_S = 20
START = datetime(2027, 1, 12, 17, 0, tzinfo=timezone(timedelta(hours=1)))


class House:
    """Very small physical model. Times in minutes since START."""

    def __init__(self, cooker=(), base_kw=0.4, car=True, pool=True, heater=True, pv_kw=0.0, battery=False, soc=80.0, throttle=False, comfort=21.0):
        self.cooker = list(cooker)        # (from_min, to_min, kw); cooker cycles 40 s on / 20 s off
        self.base_kw = base_kw
        self.pv_kw = pv_kw
        self.car_wants = car
        self.current = 16
        self.phase_option = "Auto"
        self.car_kw = 0.0
        self.pause_until = -1.0
        self.pool_on = pool
        self.heater_on = heater
        self.counter_kwh = 1000.0
        self.min_current_seen = 99
        self.car_stopped_by_guard = False
        self.has_battery = battery
        self.soc = soc
        self.bat_released = False  # released battery feeds the house with 0.8 kW
        self.has_throttle = throttle  # a heat pump with a power limit in percent: 3 kW at 100 %
        self.thr_value = 100.0
        self.comfort = comfort
        self.deaf_wb = False       # the wallbox accepts no commands (cloud problem, wrong entity ...)

    def _car_setpoint_kw(self) -> float:
        if not self.car_wants:
            return 0.0
        v = engine.V1 if self.phase_option == "1 Phase" else engine.V3
        return self.current * v / 1000.0

    def advance(self, t_min: float) -> float:
        cook = 0.0
        for a, b, kw in self.cooker:
            if a <= t_min < b and (t_min * 60) % 60 < 40:
                cook += kw
        if t_min < self.pause_until:
            self.car_kw = 0.0
        else:
            self.car_kw += (self._car_setpoint_kw() - self.car_kw) * 0.7  # car follows within ~20-40 s
        load = self.base_kw + cook + self.car_kw + (0.75 if self.pool_on else 0.0) + (2.0 if self.heater_on else 0.0)
        if self.has_throttle:
            load += self.thr_power_kw()
        grid = max(0.0, load - self.pv_kw - (0.8 if self.bat_released else 0.0))
        self.counter_kwh += grid * STEP_S / 3600.0
        return grid

    def thr_power_kw(self) -> float:
        return 3.0 * self.thr_value / 100.0

    def readings(self) -> dict:
        R = engine.Reading
        extra = {"bat": R(soc=self.soc, releasable=not self.bat_released)} if self.has_battery else {}
        if self.has_throttle:
            extra["hp"] = R(power_w=self.thr_power_kw() * 1000, value=self.thr_value, soc=self.comfort)
        return {**extra,
            "wb": R(power_w=self.car_kw * 1000, current_a=self.current, phase_option=self.phase_option,
                    phases=1 if self.phase_option == "1 Phase" else 3),
            "pool": R(power_w=750.0 if self.pool_on else 0.0, is_on=self.pool_on),
            "heater": R(power_w=2000.0 if self.heater_on else 0.0, is_on=self.heater_on),
        }

    def apply(self, a, t_min: float) -> None:
        if a.device_id == "wb":
            if self.deaf_wb:
                return
            if a.kind == "set_current":
                self.current = int(a.value)
                self.min_current_seen = min(self.min_current_seen, self.current)
            elif a.kind == "set_phase" and a.value != self.phase_option:
                self.phase_option = a.value
                self.pause_until = t_min + 1.0  # phase switch: about a minute without charging
        elif a.kind == "set_value" and a.device_id == "hp":
            self.thr_value = float(a.value)
        elif a.kind in ("battery_release", "battery_restore"):
            self.bat_released = a.kind == "battery_release"
        elif a.kind in ("turn_off", "turn_on"):
            setattr(self, "pool_on" if a.device_id == "pool" else "heater_on", a.kind == "turn_on")


def devices(prio_wb=1, prio_pool=2, prio_heater=3, pool_max_off=0.0, battery=False, throttle_prio=None, **hp):
    D = engine.DeviceConfig
    bat = [D(id="bat", name="Batterie", kind="battery", priority=10, power_w=800, min_soc=30)] if battery else []
    thr = [D(id="hp", name="Waermepumpe", kind="throttle", priority=throttle_prio, min_value=30, max_value=100, step=10,
            power_w=3000, **{"min_soc": 0.0, **hp})] if throttle_prio is not None else []
    return bat + thr + [
        D(id="wb", name="Wallbox", kind="wallbox", priority=prio_wb, one_phase_option="1 Phase"),
        D(id="pool", name="Pool", kind="switch", priority=prio_pool, min_power_w=150, max_off_min=pool_max_off),
        D(id="heater", name="Boiler", kind="switch", priority=prio_heater, min_power_w=300),
    ]


def run(house: House, guard, minutes: int, limit=10.0, margin=0.5, grid_gap=None, verbose=False, unguarded=None,
        finished=None):
    """Returns (quarter averages in kW, log of action texts).

    `unguarded` collects the guard's estimate without intervention per quarter, `finished` the guard's own measured
    quarter averages (they differ slightly from the simulation because the guard integrates 20 s samples)."""
    quarters, log = [], []
    q_energy, q_start = 0.0, START
    for i in range(int(minutes * 60 / STEP_S)):
        t_min = i * STEP_S / 60.0
        now = START + timedelta(minutes=t_min)
        if now - q_start >= timedelta(minutes=15):
            quarters.append(q_energy / 0.25)
            q_energy, q_start = 0.0, q_start + timedelta(minutes=15)
        grid = house.advance(t_min)
        q_energy += grid * STEP_S / 3600.0
        missing = grid_gap is not None and grid_gap[0] <= t_min < grid_gap[1]
        acts = guard.step(now, None if missing else grid, None if missing else house.counter_kwh,
                          house.readings(), limit, margin, True)
        if unguarded is not None and guard.finished_unguarded_kw is not None:
            unguarded.append(guard.finished_unguarded_kw)
        if finished is not None and guard.finished_quarter_kw is not None:
            finished.append(guard.finished_quarter_kw)
        for a in acts:
            house.apply(a, t_min)
            if a.text:
                log.append(f"{now:%H:%M:%S} {a.text}")
                if verbose:
                    print(log[-1])
    quarters.append(q_energy / 0.25)
    return quarters, log


if __name__ == "__main__":
    h = House(cooker=[(5, 35, 7.0)])
    qs, _ = run(h, engine.Guard(devices()), 60, verbose=True)
    print("Viertelstunden kW:", [round(x, 2) for x in qs])
    print("Wallbox am Ende:", h.current, "A", h.phase_option, "| kleinster Strom:", h.min_current_seen, "A")
