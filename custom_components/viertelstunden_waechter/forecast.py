"""Load forecast: the typical grid import per weekday and quarter hour, learned from the past (pure Python).

Every finished quarter hour adds a sample (kW) to its slot (weekday x quarter of the day). A slot keeps the last
`MAX_SAMPLES` samples, so the model follows the habits of the last weeks. The history can be bootstrapped from
hourly statistics (an hourly mean is a lower bound for its four quarters, so peaks are underestimated at first).

Per slot:  typical = median,  high = second highest sample (the highest if fewer than four samples).
A quarter hour is a *risk* if its `high` exceeds the target and at least `MIN_SAMPLES` samples exist.

With a wallbox the guard learns two models from the same quarter hours: the house without the wallbox and the wallbox
alone. `combine()` adds them sample by sample (the total as before); when the car is full or not plugged in, the house
model alone is the forecast, so a usual evening charging does not show as a risk on a day it cannot happen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any

SLOTS_PER_DAY = 96
MAX_SAMPLES = 8
MIN_SAMPLES = 2
MAX_PLAUSIBLE_KW = 60.0

HEAT_BELOW_C = 15.0      # heating starts to add load below this outdoor temperature
COOL_ABOVE_C = 22.0      # air conditioning starts to add load above it
FIT_MIN_DAYS = 14
FIT_MIN_SPREAD = 20.0    # sum of squared degrees below/above the balance point needed to fit a slope


@dataclass(frozen=True)
class WeatherCurve:
    """Extra house load (kW, mean over the day) per kelvin below `heat_below` and above `cool_above`."""

    heat_kw_per_k: float = 0.0
    cool_kw_per_k: float = 0.0
    heat_below: float = HEAT_BELOW_C
    cool_above: float = COOL_ABOVE_C

    def extra(self, temp: float) -> float:
        return (self.heat_kw_per_k * max(0.0, self.heat_below - temp)
                + self.cool_kw_per_k * max(0.0, temp - self.cool_above))

    @property
    def active(self) -> bool:
        return self.heat_kw_per_k > 0.0 or self.cool_kw_per_k > 0.0


def fit_curve(days: list[tuple[int, float, float]]) -> tuple[WeatherCurve, dict[str, Any]]:
    """Fit the weather curve from daily records (weekday, mean house kW, mean outdoor temperature).

    The weekday mean is removed first (the weekly habit is the model's job), then the rest is regressed on the heating
    degrees (`HEAT_BELOW_C - T`) and the cooling degrees (`T - COOL_ABOVE_C`). Slopes are never negative. A slope is
    only fitted if the days show enough spread in its range; otherwise it stays 0 (no correction)."""
    info: dict[str, Any] = {"days": len(days), "heat": 0.0, "cool": 0.0, "r2": 0.0}
    if len(days) < FIT_MIN_DAYS:
        return WeatherCurve(0.0, 0.0), info
    # within-weekday regression: remove each weekday's mean from the load AND from the degrees
    groups: dict[int, list[tuple[float, float, float]]] = {}
    for wd, kw, t in days:
        groups.setdefault(wd, []).append((max(0.0, HEAT_BELOW_C - t), max(0.0, t - COOL_ABOVE_C), kw))
    rows = []
    for g in groups.values():
        mh, mc, my = (sum(x[i] for x in g) / len(g) for i in range(3))
        rows += [(h - mh, c - mc, y - my) for h, c, y in g]
    shh = sum(h * h for h, _, _ in rows)
    scc = sum(c * c for _, c, _ in rows)
    shc = sum(h * c for h, c, _ in rows)
    shy = sum(h * y for h, _, y in rows)
    scy = sum(c * y for _, c, y in rows)
    use_h = shh >= FIT_MIN_SPREAD
    use_c = scc >= FIT_MIN_SPREAD
    a = b = 0.0
    if use_h and use_c:
        det = shh * scc - shc * shc
        if abs(det) > 1e-9:
            a, b = (shy * scc - scy * shc) / det, (scy * shh - shy * shc) / det
        else:
            a = shy / shh
    elif use_h:
        a = shy / shh
    elif use_c:
        b = scy / scc
    a, b = max(0.0, a), max(0.0, b)
    ss_tot = sum(y * y for _, _, y in rows)
    ss_res = sum((y - a * h - b * c) ** 2 for h, c, y in rows)
    info.update({"heat": round(a, 4), "cool": round(b, 4), "r2": round(1 - ss_res / ss_tot, 3) if ss_tot > 0 else 0.0})
    return WeatherCurve(round(a, 4), round(b, 4)), info


def slot_of(when: datetime) -> int:
    return when.weekday() * SLOTS_PER_DAY + (when.hour * 60 + when.minute) // 15


def floor_quarter(when: datetime) -> datetime:
    return when.replace(minute=(when.minute // 15) * 15, second=0, microsecond=0)


class LoadModel:
    def __init__(self, slots: dict[int, list[float]] | None = None,
                 temps: dict[int, list[float | None]] | None = None) -> None:
        self.slots: dict[int, list[float]] = slots or {}
        # outdoor temperature at each sample, same order and length as `slots` (None = not known);
        # only used by the weather correction
        self.temps: dict[int, list[float | None]] = dict(temps or {})
        for k, v in self.slots.items():
            t = self.temps.get(k, [])
            self.temps[k] = ([None] * (len(v) - len(t)) + list(t))[-len(v):] if v else []

    # ---------- learning ----------

    def add(self, when: datetime, kw: float, temp: float | None = None) -> None:
        if kw is None or kw < 0 or kw > MAX_PLAUSIBLE_KW:
            return  # counter jumps after an outage are not real load
        k = slot_of(when)
        lst = self.slots.setdefault(k, [])
        tl = self.temps.setdefault(k, [None] * len(lst))
        lst.append(round(float(kw), 3))
        tl.append(round(float(temp), 1) if temp is not None else None)
        del lst[:-MAX_SAMPLES]
        del tl[:-MAX_SAMPLES]

    def add_hourly(self, hour_start: datetime, kw: float, temp: float | None = None) -> None:
        for q in range(4):
            self.add(hour_start + timedelta(minutes=15 * q), kw, temp)

    @property
    def samples(self) -> int:
        return sum(len(v) for v in self.slots.values())

    @property
    def slots_with_data(self) -> int:
        return sum(1 for v in self.slots.values() if v)

    # ---------- predicting ----------

    def predict(self, when: datetime, temp: float | None = None,
                curve: WeatherCurve | None = None) -> tuple[float, float, int] | None:
        """(typical, high, number of samples) for the quarter hour containing `when`, or None without data.

        With a weather curve and the expected outdoor temperature every sample is moved to that temperature first
        (`kw + extra(expected) - extra(temperature at the sample)`); samples without a temperature stay as they are."""
        k = slot_of(when)
        values = self.slots.get(k)
        if not values:
            return None
        if curve is not None and curve.active and temp is not None:
            ts = self.temps.get(k) or [None] * len(values)
            now_extra = curve.extra(temp)
            values = [max(0.0, v + now_extra - curve.extra(t)) if t is not None else v for v, t in zip(values, ts)]
        s = sorted(values)
        return round(median(s), 3), round(s[-2] if len(s) >= 4 else s[-1], 3), len(s)

    def horizon(self, now: datetime, hours: int = 24, temp_at: Callable[[datetime], float | None] | None = None,
                curve: WeatherCurve | None = None) -> list[dict[str, Any]]:
        start = floor_quarter(now)
        out = []
        for i in range(hours * 4):
            t = start + timedelta(minutes=15 * i)
            p = self.predict(t, temp_at(t) if temp_at else None, curve)
            out.append({"t": t, "typical": p[0] if p else None, "high": p[1] if p else None, "n": p[2] if p else 0})
        return out

    # ---------- persistence ----------

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"slots": {str(k): v for k, v in self.slots.items() if v}}
        temps = {str(k): v for k, v in self.temps.items() if v and any(x is not None for x in v)}
        if temps:
            d["temps"] = temps
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LoadModel:
        slots: dict[int, list[float]] = {}
        for k, v in (d.get("slots") or {}).items():
            try:
                slots[int(k)] = [float(x) for x in v][-MAX_SAMPLES:]
            except (TypeError, ValueError):
                continue
        temps: dict[int, list[float | None]] = {}
        for k, v in (d.get("temps") or {}).items():
            try:
                temps[int(k)] = [None if x is None else float(x) for x in v][-MAX_SAMPLES:]
            except (TypeError, ValueError):
                continue
        return cls(slots, temps)


RESERVE_CAP_KW = 3.0
RESERVE_MIN_KW = 0.5
RESERVE_MIN_SAMPLES = 3


def reserve_kw(model: LoadModel, when: datetime, target_kw: float, cap: float = RESERVE_CAP_KW,
               temp: float | None = None, curve: WeatherCurve | None = None) -> tuple[float, dict[str, Any] | None]:
    """Headroom the guard keeps free in a risk quarter hour (the forecast `high` exceeds the target): the usual
    spike on top of the typical value (`high - typical`, at most `cap`). 0 for a normal quarter hour or too little data."""
    p = model.predict(when, temp, curve)
    if p is None or p[2] < RESERVE_MIN_SAMPLES or p[1] <= target_kw:
        return 0.0, None
    spike = min(cap, max(0.0, p[1] - p[0]))
    if spike < RESERVE_MIN_KW:
        return 0.0, None
    return round(spike, 2), {"typical": p[0], "high": p[1], "n": p[2]}


def combine(house: LoadModel, wallbox: LoadModel) -> LoadModel:
    """House plus wallbox, sample by sample. Both learn the same quarter hours, so the lists are aligned at their end;
    older house samples without a wallbox part (history import, data from before the split) are totals already."""
    slots: dict[int, list[float]] = {}
    temps: dict[int, list[float | None]] = {}
    for slot in set(house.slots) | set(wallbox.slots):
        h = house.slots.get(slot, [])
        w = wallbox.slots.get(slot, [])
        n = max(len(h), len(w))
        h = [0.0] * (n - len(h)) + h
        w = [0.0] * (n - len(w)) + w
        slots[slot] = [round(a + b, 3) for a, b in zip(h, w)][-MAX_SAMPLES:]
        ht = house.temps.get(slot, [])
        temps[slot] = ([None] * (n - len(ht)) + list(ht))[-MAX_SAMPLES:]  # the correction is additive: the house part carries it
    return LoadModel(slots, temps)


def reserve_window(windows: list[dict[str, Any]], now: datetime, lead_min: float) -> dict[str, Any] | None:
    """The risk window that is running or starts within `lead_min` minutes, else None."""
    for w in windows:
        if w["start"] - timedelta(minutes=lead_min) <= now < w["end"]:
            return w
    return None


def risk_windows(series: list[dict[str, Any]], target_kw: float, min_samples: int = MIN_SAMPLES) -> list[dict[str, Any]]:
    """Merge consecutive risk quarter hours into windows (start, end, highest `high`, highest typical)."""
    windows: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for q in series:
        risky = q["high"] is not None and q["n"] >= min_samples and q["high"] > target_kw
        if risky:
            end = q["t"] + timedelta(minutes=15)
            if cur is not None and cur["end"] == q["t"]:
                cur["end"] = end
                cur["high_kw"] = max(cur["high_kw"], q["high"])
                cur["typical_kw"] = max(cur["typical_kw"], q["typical"])
            else:
                cur = {"start": q["t"], "end": end, "high_kw": q["high"], "typical_kw": q["typical"]}
                windows.append(cur)
        else:
            cur = None
    return windows


def hourly(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Condense the quarter-hour series to hours: mean of the typical values, maximum of the high values."""
    out: list[dict[str, Any]] = []
    for i in range(0, len(series), 4):
        chunk = [q for q in series[i:i + 4] if q["typical"] is not None]
        if not chunk:
            out.append({"t": series[i]["t"], "typical": None, "high": None})
            continue
        out.append({"t": series[i]["t"], "typical": round(sum(q["typical"] for q in chunk) / len(chunk), 2),
                    "high": round(max(q["high"] for q in chunk), 2)})
    return out


def weekly_profile(model: LoadModel) -> list[dict[str, Any]]:
    """Per weekday (0 = Monday) 24 hourly values: `typical` = mean of the four typical quarter hours, `high` = highest
    `high` of the four. Hours without data are None. For sparkline-like displays of the usual week."""
    out: list[dict[str, Any]] = []
    for wd in range(7):
        typical: list[float | None] = []
        high: list[float | None] = []
        for h in range(24):
            tv: list[float] = []
            hv: list[float] = []
            for q in range(4):
                values = model.slots.get(wd * SLOTS_PER_DAY + h * 4 + q)
                if values:
                    s = sorted(values)
                    tv.append(median(s))
                    hv.append(s[-2] if len(s) >= 4 else s[-1])
            typical.append(round(sum(tv) / len(tv), 2) if tv else None)
            high.append(round(max(hv), 2) if hv else None)
        out.append({"day": wd, "typical": typical, "high": high})
    return out
