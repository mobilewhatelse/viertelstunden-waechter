"""Load forecast: the typical grid import per weekday and quarter hour, learned from the past (pure Python).

Every finished quarter hour adds a sample (kW) to its slot (weekday x quarter of the day). A slot keeps the last
`MAX_SAMPLES` samples, so the model follows the habits of the last weeks. The history can be bootstrapped from
hourly statistics (an hourly mean is a lower bound for its four quarters, so peaks are underestimated at first).

Per slot:  typical = median,  high = second highest sample (the highest if fewer than four samples).
A quarter hour is a *risk* if its `high` exceeds the target and at least `MIN_SAMPLES` samples exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any

SLOTS_PER_DAY = 96
MAX_SAMPLES = 8
MIN_SAMPLES = 2
MAX_PLAUSIBLE_KW = 60.0


def slot_of(when: datetime) -> int:
    return when.weekday() * SLOTS_PER_DAY + (when.hour * 60 + when.minute) // 15


def floor_quarter(when: datetime) -> datetime:
    return when.replace(minute=(when.minute // 15) * 15, second=0, microsecond=0)


class LoadModel:
    def __init__(self, slots: dict[int, list[float]] | None = None) -> None:
        self.slots: dict[int, list[float]] = slots or {}

    # ---------- learning ----------

    def add(self, when: datetime, kw: float) -> None:
        if kw is None or kw < 0 or kw > MAX_PLAUSIBLE_KW:
            return  # counter jumps after an outage are not real load
        lst = self.slots.setdefault(slot_of(when), [])
        lst.append(round(float(kw), 3))
        del lst[:-MAX_SAMPLES]

    def add_hourly(self, hour_start: datetime, kw: float) -> None:
        for q in range(4):
            self.add(hour_start + timedelta(minutes=15 * q), kw)

    @property
    def samples(self) -> int:
        return sum(len(v) for v in self.slots.values())

    @property
    def slots_with_data(self) -> int:
        return sum(1 for v in self.slots.values() if v)

    # ---------- predicting ----------

    def predict(self, when: datetime) -> tuple[float, float, int] | None:
        """(typical, high, number of samples) for the quarter hour containing `when`, or None without data."""
        values = self.slots.get(slot_of(when))
        if not values:
            return None
        s = sorted(values)
        return round(median(s), 3), s[-2] if len(s) >= 4 else s[-1], len(s)

    def horizon(self, now: datetime, hours: int = 24) -> list[dict[str, Any]]:
        start = floor_quarter(now)
        out = []
        for i in range(hours * 4):
            t = start + timedelta(minutes=15 * i)
            p = self.predict(t)
            out.append({"t": t, "typical": p[0] if p else None, "high": p[1] if p else None, "n": p[2] if p else 0})
        return out

    # ---------- persistence ----------

    def to_dict(self) -> dict[str, Any]:
        return {"slots": {str(k): v for k, v in self.slots.items() if v}}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LoadModel:
        slots: dict[int, list[float]] = {}
        for k, v in (d.get("slots") or {}).items():
            try:
                slots[int(k)] = [float(x) for x in v][-MAX_SAMPLES:]
            except (TypeError, ValueError):
                continue
        return cls(slots)


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
