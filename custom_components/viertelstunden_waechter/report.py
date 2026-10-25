"""Weekly report (pure Python, no Home Assistant imports)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

TEXTS = {
    "de": {
        "title": "Wochenbericht {label}",
        "peak": "Höchste Viertelstunde: {kw:.1f} kW am {day}{at}",
        "no_data": "Für diese Woche liegen keine Messwerte vor.",
        "over": "Tage über der Grenze ({limit:.1f} kW): {n} von {days}",
        "ivs": "Eingriffe: {real}",
        "shadow": ", beobachtet (ohne Wirkung): {shadow}",
        "miss": "Befehle, die ein Gerät nicht umgesetzt hat: {miss}",
        "month": "Spitze im Monat {month}: {kw:.1f} kW",
        "cost": "Leistungspreis {month}: {cost:.2f}, geschätzte Ersparnis: {saving:.2f}",
    },
    "en": {
        "title": "Weekly report {label}",
        "peak": "Highest quarter hour: {kw:.1f} kW on {day}{at}",
        "no_data": "No measurements for this week.",
        "over": "Days above the limit ({limit:.1f} kW): {n} of {days}",
        "ivs": "Interventions: {real}",
        "shadow": ", observed (no effect): {shadow}",
        "miss": "Commands a device did not carry out: {miss}",
        "month": "Peak in {month}: {kw:.1f} kW",
        "cost": "Demand charge {month}: {cost:.2f}, estimated saving: {saving:.2f}",
    },
}


def week_label(start: date) -> str:
    iso = start.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_report(
    day_peaks: dict[str, dict[str, Any]],
    counts: dict[str, dict[str, int]],
    limit_kw: float,
    start: date,
    days: int = 7,
    month_peak_kw: float | None = None,
    month_costs: dict[str, float | None] | None = None,
    lang: str = "de",
) -> dict[str, Any]:
    """Summary of the `days` days from `start` (a Monday for a full week)."""
    x = TEXTS["en" if not lang.startswith("de") else "de"]
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    peaks = {d: day_peaks[d] for d in dates if d in day_peaks}
    top_day = max(peaks, key=lambda d: float(peaks[d].get("kw") or 0.0), default=None)
    real = sum(int(counts.get(d, {}).get("real", 0)) for d in dates)
    shadow = sum(int(counts.get(d, {}).get("shadow", 0)) for d in dates)
    miss = sum(int(counts.get(d, {}).get("miss", 0)) for d in dates)
    over = sum(1 for d in peaks.values() if float(d.get("kw") or 0.0) > limit_kw)
    month = (start + timedelta(days=days - 1)).strftime("%Y-%m")
    lines = [x["title"].format(label=f"{week_label(start)} ({start:%d.%m.}–{start + timedelta(days=days - 1):%d.%m.})")]
    if top_day is None:
        lines.append(x["no_data"])
    else:
        t = peaks[top_day].get("at")
        lines.append(x["peak"].format(kw=float(peaks[top_day]["kw"]), day=f"{top_day[8:10]}.{top_day[5:7]}.", at=f" {t}" if t else ""))
        lines.append(x["over"].format(limit=limit_kw, n=over, days=len(peaks)))
    lines.append(x["ivs"].format(real=real) + (x["shadow"].format(shadow=shadow) if shadow else ""))
    if miss:
        lines.append(x["miss"].format(miss=miss))
    if month_peak_kw:
        lines.append(x["month"].format(month=month, kw=month_peak_kw))
    if month_costs and month_costs.get("cost") is not None:
        lines.append(x["cost"].format(month=month, cost=month_costs["cost"], saving=month_costs.get("saving") or 0.0))
    return {
        "week": week_label(start),
        "start": start.isoformat(),
        "text": "\n".join(lines),
        "peak_kw": float(peaks[top_day]["kw"]) if top_day else None,
        "peak_day": top_day,
        "days_over": over,
        "days_with_data": len(peaks),
        "interventions": real,
        "observed": shadow,
        "unconfirmed": miss,
    }
