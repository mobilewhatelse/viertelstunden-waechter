"""Instructions for the optional AI explainer (pure Python, no Home Assistant imports).

The explainer only writes text: it gets the guard's own log of the day and a few numbers and is asked for a short,
plain explanation. It never decides or switches anything; the fixed rules of the guard do that.
"""

from __future__ import annotations

from typing import Any

TEXTS = {
    "de": {
        "role": "Du erklärst einem Hausbesitzer in einfachen Worten, was der Viertelstunden-Wächter heute getan hat. "
                "Der Wächter hält den mittleren Netzbezug jeder Viertelstunde unter einer Grenze (Leistungspreis), indem er "
                "z. B. den Ladestrom der Wallbox senkt oder Geräte kurz abschaltet und danach alles zurückgibt.",
        "rules": "Schreibe 2 bis 4 kurze Sätze auf Deutsch, ohne Fachbegriffe wie Budget oder Engine. Nenne, wann und warum "
                 "eingegriffen wurde, was betroffen war und ob die Grenze gehalten wurde. Erfinde nichts, nutze nur die Daten "
                 "unten. Gib keine Anweisungen und keine Ratschläge zum Schalten. Keine Überschrift, keine Aufzählung.",
        "data": "Daten des Tages",
        "date": "Datum", "limit": "Grenze", "target": "Ziel", "peak": "höchste Viertelstunde heute", "at": "um",
        "count": "Eingriffe", "misses": "Befehle ohne Wirkung", "log": "Protokoll des Wächters (neueste zuerst)",
        "observed": "Hinweis: Der Wächter war im Beobachtungsmodus; mit (beobachtet) markierte Zeilen wurden nicht ausgeführt.",
    },
    "en": {
        "role": "You explain to a home owner in plain words what the quarter-hour peak guard did today. The guard keeps the "
                "average grid import of every quarter hour below a limit (demand charge) by, for example, lowering the "
                "wallbox current or switching devices off for a while, and gives everything back afterwards.",
        "rules": "Write 2 to 4 short sentences in English, without technical terms like budget or engine. Say when and why it "
                 "intervened, what was affected and whether the limit held. Do not invent anything, use only the data below. "
                 "Give no instructions and no advice on switching. No heading, no list.",
        "data": "Data of the day",
        "date": "Date", "limit": "Limit", "target": "Target", "peak": "highest quarter hour today", "at": "at",
        "count": "Interventions", "misses": "Commands without effect", "log": "Guard log (newest first)",
        "observed": "Note: the guard was in observe mode; lines marked (observed) were not carried out.",
    },
}


def build_instructions(lang: str, day: str, lines: list[str], limit_kw: float, target_kw: float,
                       peak_kw: float | None, peak_at: str | None, interventions: int, misses: int,
                       observed: bool) -> str:
    x = TEXTS["de" if str(lang).startswith("de") else "en"]
    data = [
        f"{x['date']}: {day}",
        f"{x['limit']}: {limit_kw:.1f} kW, {x['target']}: {target_kw:.1f} kW",
        f"{x['peak']}: {peak_kw:.2f} kW" + (f" {x['at']} {peak_at}" if peak_at else "") if peak_kw is not None else "",
        f"{x['count']}: {interventions}, {x['misses']}: {misses}",
    ]
    log = "\n".join(f"- {line}" for line in lines[:40])
    parts = [x["role"], x["rules"], "", x["data"] + ":", *[d for d in data if d], "", x["log"] + ":", log]
    if observed:
        parts += ["", x["observed"]]
    return "\n".join(parts)


def plain_summary(lang: str, interventions: int, peak_kw: float | None, limit_kw: float, day: str = "") -> str:
    """Text without AI for a day without interventions (no AI call needed)."""
    de = str(lang).startswith("de")

    def num(v: float | None) -> str:
        if v is None:
            return "-"
        return f"{v:.1f}".replace(".", ",") if de else f"{v:.1f}"

    if de:
        return f"{'Am ' + day if day else 'Heute'} musste der Wächter nicht eingreifen. Die höchste Viertelstunde lag bei {num(peak_kw)} kW (Grenze {num(limit_kw)} kW)."
    return f"The guard did not need to intervene {'on ' + day.rstrip('.') if day else 'today'}. The highest quarter hour was {num(peak_kw)} kW (limit {num(limit_kw)} kW)."


def extract_text(response: Any) -> str:
    """The text of an ai_task.generate_data response ({"data": "..."}), tolerant of other shapes."""
    if isinstance(response, dict):
        data = response.get("data", response.get("text"))
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, dict):
            for key in ("text", "explanation", "summary"):
                if isinstance(data.get(key), str):
                    return data[key].strip()
    if isinstance(response, str):
        return response.strip()
    return ""
