"""Charge plan for an electric car (pure Python, no Home Assistant imports).

Given the car's state of charge, the target, the departure time, what the wallbox can deliver, the expected house load
(learned per weekday and quarter hour) and - if available - the solar forecast, the plan decides in which quarter hours
to charge and with how much power:

1. Quarter hours with solar surplus come first (charging from the sun costs no grid energy).
2. The rest is taken from the quarter hours with the lowest expected grid import, as far as the peak target allows
   (expected import + what the car takes from the grid must stay below the target).
3. If the target cannot be reached by departure, the plan says so and how many kWh are missing - it never pretends.

The plan is advice. Executing it (pausing outside the planned windows) is a separate, optional step.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

QUARTER_H = 0.25
DEFAULT_HIGH_KW = 1.0  # expected import for a quarter hour without learned data


def needed_kwh(soc: float, target_soc: float, capacity_kwh: float, efficiency: float = 0.9) -> float:
    """Energy to draw from the wallbox to bring the car from `soc` to `target_soc` (percent)."""
    return max(0.0, (target_soc - soc) / 100.0 * capacity_kwh) / max(0.3, min(1.0, efficiency))


def make_plan(
    now: datetime,
    departure: datetime,
    soc: float,
    target_soc: float,
    capacity_kwh: float,
    max_kw: float,
    min_kw: float,
    target_kw: float,
    load: list[dict[str, Any]],
    solar_kw: dict[datetime, float] | None = None,
    base_kw: float = 0.5,
    efficiency: float = 0.9,
) -> dict[str, Any]:
    """Return the plan. `load` is a list of quarter hours {t, typical, high, n} (see forecast.LoadModel.horizon);
    `solar_kw` maps a quarter-hour start to the forecast PV power in kW (None = no solar forecast available)."""
    need = needed_kwh(soc, target_soc, capacity_kwh, efficiency)
    result: dict[str, Any] = {
        "status": "planned", "needed_kwh": round(need, 2), "planned_kwh": 0.0, "solar_kwh": 0.0, "grid_kwh": 0.0,
        "shortfall_kwh": 0.0, "windows": [], "quarters": {}, "ready_at": None, "latest_start": None,
        "solar_used": solar_kw is not None, "departure": departure,
    }
    if departure <= now:
        result["status"] = "no_departure"
        return result
    if need < 0.05:
        result["status"] = "not_needed"
        return result
    result["latest_start"] = departure - timedelta(hours=need / max_kw) if max_kw > 0 else None

    # usable quarter hours until departure, the running one only with its remaining part
    quarters = []
    for q in load:
        start, end = q["t"], q["t"] + timedelta(minutes=15)
        if end <= now or start >= departure:
            continue
        frac = (min(end, departure) - max(start, now)).total_seconds() / 900.0
        if frac <= 0.05:
            continue
        high = q["high"] if q["high"] is not None else DEFAULT_HIGH_KW
        surplus = max(0.0, solar_kw.get(start, 0.0) - base_kw) if solar_kw is not None else 0.0
        quarters.append({"t": start, "frac": frac, "high": high, "surplus": surplus})

    plan: dict[datetime, dict[str, float]] = {}
    remaining = need

    # 1. solar: charge with what the sun delivers beyond the house base load
    for q in sorted(quarters, key=lambda x: -x["surplus"]):
        if remaining < 0.05 or q["surplus"] < min_kw:
            continue
        p = min(max_kw, q["surplus"], remaining / (QUARTER_H * q["frac"]))
        if p < min_kw:
            p = min_kw
        plan[q["t"]] = {"kw": p, "solar": min(p, q["surplus"]), "frac": q["frac"], "grid": max(0.0, p - q["surplus"])}
        remaining -= p * QUARTER_H * q["frac"]

    # 2. grid: the quietest quarter hours first, as far as the peak target allows
    for q in sorted(quarters, key=lambda x: x["high"]):
        if remaining < 0.05:
            break
        if q["t"] in plan:
            continue
        room = target_kw - q["high"] + q["surplus"]
        p = min(max_kw, room, remaining / (QUARTER_H * q["frac"]))
        if room < min_kw:
            continue
        if p < min_kw:
            p = min_kw  # a wallbox cannot charge below its minimum; small overshoot is accepted
        plan[q["t"]] = {"kw": p, "solar": min(p, q["surplus"]), "frac": q["frac"], "grid": max(0.0, p - q["surplus"])}
        remaining -= p * QUARTER_H * q["frac"]

    solar = sum(v["solar"] * QUARTER_H * v["frac"] for v in plan.values())
    total = sum(v["kw"] * QUARTER_H * v["frac"] for v in plan.values())
    result.update({
        "planned_kwh": round(total, 2), "solar_kwh": round(solar, 2), "grid_kwh": round(max(0.0, total - solar), 2),
        "shortfall_kwh": round(max(0.0, remaining), 2),
        "quarters": {t: round(v["kw"], 2) for t, v in plan.items()},
    })
    if remaining > 0.1:
        result["status"] = "infeasible"

    # merge consecutive quarter hours into windows
    cur: dict[str, Any] | None = None
    for t in sorted(plan):
        v = plan[t]
        end = t + timedelta(minutes=15)
        if cur is not None and cur["end"] == t:
            cur["end"] = end
            cur["energy_kwh"] += v["kw"] * QUARTER_H * v["frac"]
            cur["solar_kwh"] += v["solar"] * QUARTER_H * v["frac"]
            cur["peak_kw"] = max(cur["peak_kw"], v["kw"])
        else:
            cur = {"start": t, "end": end, "energy_kwh": v["kw"] * QUARTER_H * v["frac"],
                   "solar_kwh": v["solar"] * QUARTER_H * v["frac"], "peak_kw": v["kw"]}
            result["windows"].append(cur)
    for w in result["windows"]:
        w["energy_kwh"] = round(w["energy_kwh"], 2)
        w["solar_kwh"] = round(w["solar_kwh"], 2)
        w["peak_kw"] = round(w["peak_kw"], 2)
    if result["windows"]:
        result["ready_at"] = result["windows"][-1]["end"]
    return result


def charging_allowed(plan: dict[str, Any], now: datetime) -> bool | None:
    """True if the plan wants the car to charge in the quarter hour containing `now`, False if it wants a pause,
    None if the plan does not decide (not needed, infeasible, no departure): then charging stays as it is."""
    if plan.get("status") != "planned":
        return None
    q = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    return q in plan.get("quarters", {})
