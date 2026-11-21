"""Bug report on request (button 'Send bug report'): what helps to find an error, never who.

Only on a press, independent of 'Share anonymous data'; the notification afterwards shows exactly what was sent. Never names,
entity ids, addresses, IPs or values that identify a home. Entity ids in texts become their kind ("select.wallbox_mode" ->
"select"), names of devices become "<name>", no clock times (the history says "vor 2.0 h").
Same build as in Plugwhen. Pure functions here (tested without Home Assistant); the coordinator collects the raw values.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from datetime import datetime
from typing import Any

MAX_LINES = 20         # warnings kept (only in memory, gone after a restart)
SLOW_S = 15            # a command taking longer counts as slow (a device over its cloud)
MAX_BYTES = 8000       # the server takes 16 KB with the text; the oldest log lines go first

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_MAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
_ENTITY = re.compile(r"\b([a-z][a-z0-9_]*)\.[a-z0-9_]+\b")
# entry ids (ULID, hex), serials, vehicle identification numbers: long runs of letters and digits with at least one digit
_LONG_ID = re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{12,}\b")

_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[+-]\d{2}:?\d{2}|Z)?")
_CLOCK = re.compile(r"(?<![\d.:])\d{1,2}:\d{2}(?::\d{2})?(?![\d:])")
# an option of a select that is a number, also with a comma or a unit ("6", "1,5 kW", "16 A", "80 %")
_NUMBER_OPTION = re.compile(r"[+-]?\d+(?:[.,]\d+)?\s*(?:%|°c|°f|a|ma|v|w|kw|wh|kwh|h|min|s|km|km/h|mi|ct|€)?", re.I)


def real_names(names: list[str] | None, keep: list[str] | None) -> list[str]:
    """Only names that can identify somebody: a name that is part of a kind, an integration, a maker or a model ("Wallbox",
    "Mercedes" in "Mercedes-Benz") is just a word, replacing it would erase what the report is for."""
    words = [str(k).lower() for k in (keep or []) if k]
    return [n for n in (names or []) if n and not any(n.strip().lower() in w for w in words)]


def _plain_option(option: str, keep: list[str] | None) -> bool:
    return bool(_NUMBER_OPTION.fullmatch(option.strip())) or not real_names([option], keep)


def select_text(current: Any, options: Any, keep: list[str] | None = None) -> str:
    """A select in the report: the current option and the list only when every option is a number (also with a unit or a comma)
    or part of the words `keep` (as in real_names). Otherwise the options are free texts the anonymiser does not know (a car
    named after its driver), then only how many there are and the position of the current one: 'Option 2 von 3 Optionen'."""
    opts = [str(o) for o in options] if isinstance(options, (list, tuple)) else []
    cur = str(current)
    if opts and all(_plain_option(o, keep) for o in opts):
        return f"{cur} von {opts}"
    if cur in ("unknown", "unavailable") or _plain_option(cur, keep):
        shown = cur
    else:
        shown = f"Option {opts.index(cur) + 1}" if cur in opts else "Option ?"
    return f"{shown} von {len(opts)} Optionen"


def anonym(text: Any, names: list[str] | None = None, limit: int = 300) -> str | None:
    """A text without what identifies anybody: names (longest first), URLs, e-mail, IPs, long ids, entity ids (kind kept)."""
    if text is None:
        return None
    t = str(text)
    for i, n in enumerate(sorted({x for x in (names or []) if x and len(x.strip()) >= 2}, key=len, reverse=True)):
        t = re.sub(re.escape(n.strip()), "<name>", t, flags=re.I)
    t = _URL.sub("<url>", t)
    t = _MAIL.sub("<mail>", t)
    t = _IP.sub("<ip>", t)
    t = _TS.sub("<zeitpunkt>", t)
    t = _CLOCK.sub("<uhrzeit>", t)
    t = _LONG_ID.sub("<id>", t)
    t = _ENTITY.sub(lambda m: m.group(1), t)
    return t.strip()[:limit]


class Calls:
    """How a device setting answers: per entity number of commands, time of the service call, failures, value taken or not."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def call(self, entity_id: str, seconds: float, error: BaseException | None = None) -> None:
        r = self.items.setdefault(entity_id, {"n": 0, "sum": 0.0, "max": 0.0, "slow": 0, "failed": 0, "errors": {}})
        r["n"] += 1
        r["sum"] += seconds
        r["max"] = max(r["max"], seconds)
        if seconds > SLOW_S:
            r["slow"] += 1
        if error is not None:
            r["failed"] += 1
            kind = type(error).__name__
            r["errors"][kind] = r["errors"].get(kind, 0) + 1

    def reply(self, entity_id: str, taken: bool, seconds: float | None) -> None:
        r = self.items.setdefault(entity_id, {"n": 0, "sum": 0.0, "max": 0.0, "slow": 0, "failed": 0, "errors": {}})
        key = "taken" if taken else "not_taken"
        r[key] = r.get(key, 0) + 1
        if taken and seconds is not None:
            r["reply_max"] = round(max(r.get("reply_max", 0.0), seconds), 1)

    def summary(self, entity_id: str) -> dict[str, Any] | None:
        r = self.items.get(entity_id)
        if not r:
            return None
        out = {"befehle": r["n"], "mittel_s": round(r["sum"] / r["n"], 1) if r["n"] else None, "laengste_s": round(r["max"], 1),
               "langsam": r["slow"], "fehlgeschlagen": r["failed"], "fehlerarten": dict(r["errors"])}
        for k, name in (("taken", "uebernommen"), ("not_taken", "nicht_uebernommen"), ("reply_max", "uebernahme_laengste_s")):
            if k in r:
                out[name] = r[k]
        return out

    def text(self, entity_id: str) -> str | None:
        """One line (the server keeps only three levels): '3 Befehle, Mittel 21.3 s, längste 25.0 s, 1 langsam, ...'."""
        s = self.summary(entity_id)
        if not s:
            return None
        parts = [f"{s['befehle']} Befehle", f"Mittel {s['mittel_s']} s", f"längste {s['laengste_s']} s", f"{s['langsam']} langsam",
                 f"{s['fehlgeschlagen']} fehlgeschlagen"]
        if s["fehlerarten"]:
            parts.append("Fehler " + ", ".join(f"{k} {v}x" for k, v in s["fehlerarten"].items()))
        if "uebernommen" in s or "nicht_uebernommen" in s:
            parts.append(f"Wert übernommen {s.get('uebernommen', 0)}, nicht übernommen {s.get('nicht_uebernommen', 0)}")
        if "uebernahme_laengste_s" in s:
            parts.append(f"Übernahme längste {s['uebernahme_laengste_s']} s")
        return ", ".join(parts)


class Lines(logging.Handler):
    """The last warnings and errors of the guard, only in memory; anonymised when the report is built, not before."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.lines: deque = deque(maxlen=MAX_LINES)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append((record.created, record.levelname, record.getMessage()))   # shown as "vor 2.0 h", never the clock
        except Exception:  # noqa: BLE001 - logging must never fail
            pass


def sensor_state(state: Any, now: datetime | None = None) -> str:
    """'ok', 'unbekannt', 'nicht_verfuegbar' or 'fehlt' (entity not there); with the age class of the last value."""
    if state is None:
        return "fehlt"
    s = str(getattr(state, "state", ""))
    if s == "unavailable":
        return "nicht_verfuegbar"
    if s in ("unknown", ""):
        return "unbekannt"
    changed = getattr(state, "last_reported", None) or getattr(state, "last_updated", None)
    if now is not None and isinstance(changed, datetime):
        h = (now - changed).total_seconds() / 3600
        return "ok" if h < 1 else "ok, älter als 1 h" if h < 24 else "ok, älter als 1 Tag"
    return "ok"


def rel_h(when: Any, now: datetime) -> str | None:
    """'vor 1.0 h' or 'in 2.5 h': no clock time, only the distance."""
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when)
        except ValueError:
            return None
    if not isinstance(when, datetime):
        return None
    h = (when - now).total_seconds() / 3600
    return f"in {h:.1f} h" if h >= 0 else f"vor {-h:.1f} h"


def ago(t: Any) -> str:
    """A log line's time (seconds since the epoch) as 'vor 2.0 h'; anything else is masked."""
    if isinstance(t, (int, float)):
        return f"vor {max(0.0, time.time() - t) / 3600:.1f} h"
    return "vor ? h"


def state_text(entity_id: str, state: Any, now: datetime) -> str:
    """What a setting says now, without a clock time: a button's last press as 'gedrückt vor 3.2 h', a time setting only as
    'gesetzt' (it would tell when somebody leaves), any other time stamp relative."""
    dom = entity_id.split(".")[0]
    s = str(getattr(state, "state", state))
    if s in ("unknown", "unavailable", ""):
        return s or "unbekannt"
    if dom in ("button", "input_button"):
        return f"gedrückt {rel_h(s, now) or '?'}"
    if dom in ("time", "input_datetime") or _CLOCK.fullmatch(s.strip()):
        return "gesetzt"
    if _TS.fullmatch(s.strip()):
        return rel_h(s, now) or "<zeitpunkt>"
    return s


def bericht(version: str, ha_version: str, einrichtung: dict[str, Any], zustand: dict[str, Any], geraete: list[dict[str, Any]],
            verlauf: list[str], zeilen: list[tuple], fehler: dict[str, Any], names: list[str],
            keep: list[str] | None = None) -> dict[str, Any]:
    """The report: everything given here is anonymised once more (a name in a log line, an id in an error text). Flat: the
    server keeps three levels, so per device only single values. `keep`: kinds, integrations, makers and models (see real_names)."""
    names = real_names(names, keep)
    def clean(x: Any) -> Any:
        if isinstance(x, dict):
            return {str(k): clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        if isinstance(x, str):
            return anonym(x, names)
        return x

    def flat(a: dict[str, Any]) -> dict[str, Any]:
        return {str(k): (v if isinstance(v, (bool, int, float)) or v is None else anonym(json.dumps(v, ensure_ascii=False)
                         if isinstance(v, (dict, list)) else v, names)) for k, v in a.items()}

    b = {"schema": 1, "version": version, "ha_version": ha_version, "einrichtung": clean(einrichtung), "zustand": flat(zustand),
         "geraete": [flat(a) for a in geraete][:20], "fehler": {k: anonym(v, names) for k, v in fehler.items() if v},
         "verlauf": [anonym(x, names, 240) for x in verlauf][:MAX_LINES],
         "protokoll": [f"{ago(t)} {lvl} {anonym(msg, names, 240)}" for t, lvl, msg in zeilen][-MAX_LINES:]}
    for key in ("protokoll", "verlauf"):   # the oldest go first
        while b[key] and len(json.dumps(b, ensure_ascii=False).encode()) > MAX_BYTES:
            b[key].pop(0 if key == "protokoll" else -1)
    return b


def anzeige(b: dict[str, Any], de: bool, gesendet: bool) -> str:
    """The notification after the press: exactly what was sent (or, if sending failed, what would have been sent)."""
    if gesendet:
        head = ("**Danke, der Fehlerbericht ist angekommen.** Gesendet wurde genau das:" if de else
                "**Thank you, the bug report was received.** Exactly this was sent:")
    else:
        head = ("**Senden hat nicht geklappt**, bitte später noch einmal. Gesendet worden wäre genau das:" if de else
                "**Sending failed**, please try again later. Exactly this would have been sent:")
    lines = [head, ""]
    lines.append(f"- Version {b['version']}, Home Assistant {b['ha_version']}")
    z = b.get("zustand") or {}
    if z:
        lines.append(("- Zustand: " if de else "- State: ") + ", ".join(f"{k}: {v}" for k, v in z.items() if v not in (None, "")))
    for i, a in enumerate(b.get("geraete") or [], 1):
        lines.append(("- Gerät " if de else "- Device ") + f"{i}: " + ", ".join(f"{k}: {v}" for k, v in a.items() if v not in (None, {}, [], "")))
    for k, v in (b.get("fehler") or {}).items():
        lines.append(f"- {k}: {v}")
    if b.get("verlauf"):
        lines += ["", "Verlauf:" if de else "History:"] + [f"    {x}" for x in b["verlauf"]]
    if b.get("protokoll"):
        lines += ["", "Protokoll:" if de else "Log:"] + [f"    {x}" for x in b["protokoll"]]
    lines += ["", ("Keine Namen, Entitäts-IDs oder Adressen. Einrichtung: " if de else "No names, entity ids or addresses. Setup: ")
              + ", ".join(f"{k} {v}" for k, v in (b.get("einrichtung") or {}).items())]
    return "\n".join(lines)
