"""Correcting a quarter hour that was recorded wrong (pure Python, no Home Assistant imports).

A quarter-hour value is the base of the day's and the month's peak and so of the demand charge. When one was recorded wrong (e.g. the
guard restarted in its middle before 0.14 and guessed), the value from the meter replaces it, and the day's and month's peaks are
worked out again from the recorded quarter hours. A month whose beginning is no longer in the record is only lowered where its peak
was exactly the wrong value - an older real peak is never removed.
"""

from __future__ import annotations

from typing import Any


def correct_quarter(quarters: list[list[Any]], day_peaks: dict[str, Any], months: dict[str, Any], month_peak: dict[str, Any],
                    start: str, kw: float) -> dict[str, Any]:
    """Set the quarter hour that begins at `start` (local time, "YYYY-MM-DDTHH:MM") to `kw` and work out the peaks again.
    Changes the arguments in place and returns what changed. Raises ValueError if there is no such quarter hour."""
    rows = [r for r in quarters if isinstance(r, list) and len(r) >= 3 and str(r[0]).startswith(start)]
    if not rows:
        raise ValueError(f"no recorded quarter hour begins at {start}")
    row = rows[0]
    old = float(row[1])
    kw = round(float(kw), 3)
    row[1] = kw
    row[2] = kw   # what it would have been without the guard is not known for a wrong value: the measured one
    day, month = str(row[0])[:10], str(row[0])[:7]

    in_day = [r for r in quarters if str(r[0])[:10] == day]
    best = max(in_day, key=lambda r: float(r[1]))
    day_peaks[day] = {"kw": float(best[1]), "at": str(best[0])[11:16]}

    in_month = [r for r in quarters if str(r[0])[:7] == month]
    top = max(in_month, key=lambda r: float(r[1]))
    covered = bool(quarters) and str(quarters[0][0])[:10] <= f"{month}-01"
    m = months.setdefault(month, {"kw": 0.0, "ug": 0.0})
    before = dict(m)
    if covered or abs(float(m.get("kw") or 0.0) - old) < 1e-3:
        m["kw"] = float(top[1])
        m["ug"] = max(float(top[1]), max(float(r[2] or 0.0) for r in in_month))
        if month_peak.get("month") == month:
            month_peak.update({"kw": float(top[1]), "at": str(top[0])})
    return {"start": str(row[0]), "old_kw": old, "new_kw": kw, "day_peak": day_peaks[day], "month": month,
            "month_before": before, "month_after": dict(m)}
