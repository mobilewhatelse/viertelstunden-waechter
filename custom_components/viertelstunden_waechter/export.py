"""CSV export of the quarter-hour load profile and the daily peaks (pure Python, no Home Assistant imports).

Two formats: `standard` (comma, decimal point - for scripts and most tools) and `excel_de` (semicolon, decimal comma -
opens directly in a German Excel). Times are local ISO timestamps of the start of the quarter hour.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

QUARTER_HEADER = ["start", "end", "import_kw", "import_kwh", "without_guard_kw", "wallbox_kw"]
DAY_HEADER = ["date", "peak_kw", "at"]


def _fmt(fmt: str):
    sep = ";" if fmt == "excel_de" else ","

    def num(v: Any, digits: int = 3) -> str:
        if v is None:
            return ""
        s = f"{float(v):.{digits}f}"
        return s.replace(".", ",") if fmt == "excel_de" else s

    return sep, num


def quarters_csv(rows: list[list[Any]], fmt: str = "standard", since: datetime | None = None) -> tuple[str, int]:
    """rows: [start_iso, import_kw, without_guard_kw, wallbox_kw] as stored by the guard. Returns (csv, row count)."""
    sep, num = _fmt(fmt)
    out = [sep.join(QUARTER_HEADER)]
    n = 0
    for r in rows:
        try:
            start = datetime.fromisoformat(str(r[0]))
        except ValueError:
            continue
        if since is not None and start < since:
            continue
        kw = r[1] if len(r) > 1 else None
        end = start + timedelta(minutes=15)
        out.append(sep.join([
            start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), num(kw),
            num(None if kw is None else float(kw) * 0.25), num(r[2] if len(r) > 2 else None),
            num(r[3] if len(r) > 3 else None),
        ]))
        n += 1
    return "\n".join(out) + "\n", n


def days_csv(day_peaks: dict[str, dict[str, Any]], fmt: str = "standard", since: str | None = None) -> tuple[str, int]:
    """day_peaks: {"2026-10-24": {"kw": 7.9, "at": "18:15"}}. Returns (csv, row count)."""
    sep, num = _fmt(fmt)
    out = [sep.join(DAY_HEADER)]
    n = 0
    for day in sorted(day_peaks):
        if since is not None and day < since:
            continue
        d = day_peaks[day]
        out.append(sep.join([day, num(d.get("kw")), str(d.get("at") or "")]))
        n += 1
    return "\n".join(out) + "\n", n
