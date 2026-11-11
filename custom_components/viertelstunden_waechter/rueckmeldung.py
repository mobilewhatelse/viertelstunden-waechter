"""Freiwillige Nutzungsstatistik und Rückmeldungen (gleiche Datei im Viertelstunden-Wächter und in Plugwhen).

Nutzungsstatistik: nur wenn der Schalter eingeschaltet ist (Standard: aus), einmal pro Woche. Gesendet werden eine zufällige
Kennung der Installation, Versionen, Land und Sprache von Home Assistant, welche Gerätearten eingerichtet sind und aus welchen
Integrationen die verwendeten Entitäten kommen (z. B. "shelly", "fronius"). Nie gesendet werden Namen, Entitäts-IDs, Adressen,
Messwerte oder Zugangsdaten. Wird der Schalter ausgeschaltet, wird einmal das Löschen der Daten dieser Kennung angefordert.

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
MAX_TEXT = 4000
MAX_KONTAKT = 200


def neue_kennung() -> str:
    return str(uuid.uuid4())


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
              einrichtung: dict[str, Any]) -> dict[str, Any]:
    return {"schema": 1, "integration": integration, "version": version, "ha_version": ha_version, "kennung": kennung,
            "land": (land or "")[:2].upper() or None, "sprache": (sprache or "")[:5] or None, "einrichtung": einrichtung}


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
