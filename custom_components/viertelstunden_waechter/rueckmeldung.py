"""Freiwillige Nutzungsstatistik und Rückmeldungen (gleiche Datei im Viertelstunden-Wächter und in Plugwhen).

Nutzungsstatistik: nur wenn der Schalter eingeschaltet ist (Standard: aus), einmal pro Woche. Gesendet werden eine zufällige
Kennung, die jeden Monat neu gezogen wird, Versionen, Land und Sprache von Home Assistant, grob wie lange die Integration schon
läuft ("0-1" … ">6" Monate), welche Gerätearten eingerichtet sind und aus welchen Integrationen die verwendeten Entitäten
kommen (z. B. "shelly", "fronius"); mit der Zustimmung Version 2 dazu verdichtete Zusatzwerte (`zusatz`). Nie gesendet werden
Namen, Entitäts-IDs, Adressen, Messwerte oder Zugangsdaten. Wird der Schalter ausgeschaltet, wird für jede gemerkte Kennung
das Löschen angefordert; die feste Kennung früherer Versionen wird beim Umstieg einmal gelöscht.

Rückmeldung: nur wenn jemand sie absendet; ihr Text, optional eine Kontaktangabe und auf Wunsch dieselbe Übersicht der Einrichtung.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

ZIEL_STATISTIK = "https://www.aiwhatelse.eu/statistik/v1/melden.php"
ZIEL_RUECKMELDUNG = "https://www.aiwhatelse.eu/statistik/v1/rueckmeldung.php"
ABSTAND = timedelta(days=7)
ABSTAND_LOESCHEN = timedelta(hours=6)   # ein misslungenes Löschen frühestens dann wieder (kein Anfragen-Sturm, wenn der Dienst fehlt)
MAX_TEXT = 4000
MAX_KONTAKT = 200


ZUSTIMMUNG = 2      # Version des Zustimmungstexts: 2 = Monatskennung, Zusatzwerte, alle Zwecke genannt
MAX_KENNUNGEN = 3   # laufender Monat und die zwei davor: der Dienst hält eine Kennung bis 60 Tage nach ihrer letzten Meldung
SEIT_KLASSEN = ((1, "0-1"), (3, "1-3"), (6, "3-6"))   # Monate -> Klasse, darüber ">6"


def neue_kennung() -> str:
    return str(uuid.uuid4())


def monat(now: datetime) -> str:
    return now.strftime("%Y-%m")


def kennung_fuer(usage: dict[str, Any], now: datetime) -> str:
    """Die Kennung dieses Monats: jeden Monat wird eine neue gezogen, die vorige bleibt nur für ein späteres Löschen gemerkt.
    So lassen sich Meldungen innerhalb eines Monats zählen, aber nicht über Monate einer Installation zuordnen."""
    liste = [k for k in usage.get("kennungen") or [] if isinstance(k, dict) and k.get("k") and k.get("monat")]
    if not liste or liste[-1]["monat"] != monat(now):
        liste.append({"k": neue_kennung(), "monat": monat(now)})
    usage["kennungen"] = liste[-MAX_KENNUNGEN:]
    return usage["kennungen"][-1]["k"]


def zu_loeschen(usage: dict[str, Any], teilen: bool) -> str | None:
    """Welche Kennung als Nächstes gelöscht werden soll, sonst None. Zuerst die alte feste Kennung früherer Versionen (beim
    Umstieg einmal, auch wenn weiter geteilt wird); nach dem Ausschalten alle gemerkten Monatskennungen."""
    if usage.get("kennung"):
        return str(usage["kennung"])
    if not teilen:
        for k in usage.get("kennungen") or []:
            if isinstance(k, dict) and k.get("k"):
                return str(k["k"])
    return None


def geloescht(usage: dict[str, Any], kennung: str) -> None:
    """Nach bestätigtem Löschen: die Kennung vergessen (Datum der letzten Meldung auch, wenn nichts mehr übrig ist)."""
    if usage.get("kennung") == kennung:
        usage.pop("kennung", None)
    usage["kennungen"] = [k for k in usage.get("kennungen") or [] if isinstance(k, dict) and k.get("k") != kennung]
    usage.pop("loeschversuch", None)
    if not usage["kennungen"]:
        usage.pop("kennungen", None)
        if not usage.get("kennung"):
            usage.pop("gesendet", None)


def loeschen_faellig(usage: dict[str, Any], now: datetime) -> bool:
    """Darf das Löschen jetzt (wieder) versucht werden? Beim ersten Mal sofort, nach einem Fehlschlag erst nach ABSTAND_LOESCHEN.
    Merkt sich den Versuch in `usage`."""
    t = None
    try:
        t = datetime.fromisoformat(usage["loeschversuch"]) if usage.get("loeschversuch") else None
    except ValueError:
        t = None
    if t is not None and t.tzinfo is None and now.tzinfo is not None:
        t = t.replace(tzinfo=now.tzinfo)
    if t is not None and now - t < ABSTAND_LOESCHEN:
        return False
    usage["loeschversuch"] = now.isoformat()
    return True


def laeuft_seit(seit: str | None, now: datetime) -> str | None:
    """Grobe Klasse, wie lange die Integration schon läuft: "0-1", "1-3", "3-6" oder ">6" Monate. Das Datum selbst bleibt lokal."""
    if not seit:
        return None
    try:
        t = datetime.fromisoformat(seit)
    except ValueError:
        return None
    if t.tzinfo is None and now.tzinfo is not None:
        t = t.replace(tzinfo=now.tzinfo)
    monate = (now - t).days / 30.44
    for grenze, klasse in SEIT_KLASSEN:
        if monate < grenze:
            return klasse
    return ">6"


def faellig(zuletzt: str | None, now: datetime) -> bool:
    """Ist eine Meldung fällig? Nie gesendet oder vor mehr als einer Woche."""
    if not zuletzt:
        return True
    try:
        t = datetime.fromisoformat(zuletzt)
    except ValueError:
        return True
    if t.tzinfo is None and now.tzinfo is not None:
        t = t.replace(tzinfo=now.tzinfo)
    return now - t >= ABSTAND


def herkunft(entity_ids: list[str], platform_of) -> list[str]:
    """Aus welchen Integrationen die verwendeten Entitäten kommen (z. B. ["fronius", "shelly"]), ohne die Entitäten selbst.
    `platform_of(entity_id)` gibt die Plattform aus der Entitätsregistrierung oder None (z. B. Template-Sensor ohne ID)."""
    out = set()
    for eid in entity_ids:
        if not isinstance(eid, str) or "." not in eid:
            continue
        p = platform_of(eid)
        out.add(str(p) if p else "ohne_registrierung")
    return sorted(out)[:30]


def statistik(integration: str, version: str, ha_version: str, kennung: str, land: str | None, sprache: str | None,
              einrichtung: dict[str, Any], seit: str | None = None, zusatz: dict[str, Any] | None = None) -> dict[str, Any]:
    d = {"schema": 1, "integration": integration, "version": version, "ha_version": ha_version, "kennung": kennung,
         "land": (land or "")[:2].upper() or None, "sprache": (sprache or "")[:5] or None, "einrichtung": einrichtung}
    if seit:
        d["laeuft_seit"] = seit
    if zusatz:
        d["zusatz"] = zusatz
    return d


def loeschen(integration: str, kennung: str) -> dict[str, Any]:
    return {"schema": 1, "integration": integration, "kennung": kennung, "loeschen": True}


def rueckmeldung(integration: str, version: str, ha_version: str, text: str, kontakt: str | None,
                 einrichtung: dict[str, Any] | None) -> dict[str, Any]:
    return {"schema": 1, "integration": integration, "version": version, "ha_version": ha_version,
            "text": str(text or "").strip()[:MAX_TEXT], "kontakt": (str(kontakt).strip()[:MAX_KONTAKT] or None) if kontakt else None,
            "einrichtung": einrichtung}


async def senden(session: Any, url: str, daten: dict[str, Any]) -> bool:
    """POST als JSON, höchstens 10 Sekunden; jeder Fehler ergibt False (die Integration läuft unverändert weiter)."""
    try:
        async with asyncio.timeout(10):
            async with session.post(url, json=daten, headers={"User-Agent": f"{daten.get('integration')}/{daten.get('version')}"}) as r:
                return 200 <= r.status < 300
    except Exception:  # noqa: BLE001 - die Statistik darf nie stören
        return False
