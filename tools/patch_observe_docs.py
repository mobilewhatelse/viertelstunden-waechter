"""One-off: documentation of 'observe only' per device and of the warning for a wallbox entered twice (kept for the record)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(rel, pairs):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8", newline="")
    crlf = "\r\n" in s
    s = s.replace("\r\n", "\n")
    for a, b in pairs:
        assert s.count(a) == 1, (rel, a[:80], s.count(a))
        s = s.replace(a, b)
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_text(s, encoding="utf-8", newline="")


EN = """
**Observe only (every device, since 0.14):** a switch in each device. The guard then only writes to the log what it would do with
that device (*Observe only: Wallbox would be lowered by 3.6 kW …*, at most once per quarter hour), sends nothing to it and does not
count it as a lever, so it does not move on to other devices because of it. Good for trying a new device (for example an evcc
loadpoint) next to the running guard.

**A wallbox entered twice:** if a *Wallbox* device and an *evcc loadpoint* charge at the same time with nearly the same power (within
15 %, over 1 kW) for two minutes, the guard writes once to the log that it is probably the same wallbox and shows it in the
attribute `wallbox_twice` of the status sensor. It changes nothing; enter the wallbox only once (as evcc loadpoint if evcc
controls it).
"""
DE = """
**Nur beobachten (jedes Gerät, seit 0.14):** ein Schalter in jedem Gerät. Der Wächter schreibt dann nur ins Protokoll, was er mit diesem Gerät
tun würde (*Nur beobachten: Wallbox würde um 3,6 kW gesenkt …*, höchstens einmal je Viertelstunde), sendet nichts und zählt das Gerät nicht als
Hebel, weicht also deshalb auch nicht auf andere Geräte aus. Gut, um ein neues Gerät (zum Beispiel einen evcc-Ladepunkt) neben dem laufenden
Wächter auszuprobieren.

**Eine Wallbox doppelt eingetragen:** Laden ein Gerät *Wallbox* und ein *evcc-Ladepunkt* zwei Minuten lang gleichzeitig mit fast gleicher Leistung
(höchstens 15 % Unterschied, über 1 kW), schreibt der Wächter einmal ins Protokoll, dass es vermutlich dieselbe Wallbox ist, und zeigt es im
Attribut `wallbox_twice` des Status-Sensors. Er ändert nichts; die Wallbox nur einmal eintragen (als evcc-Ladepunkt, wenn evcc sie steuert).
"""

edit("README.md", [("\n### Wallbox compatibility\n", EN + "\n### Wallbox compatibility\n")])
edit("docs/ANLEITUNG.md", [("### Schaltbares Gerät (aus / wieder an)\n", DE.lstrip("\n") + "\n### Schaltbares Gerät (aus / wieder an)\n")])
edit("CHANGELOG.md", [("- Installation tests: new `tests/install/itest_evcc.py`", """- **Observe only per device** (switch in every device): the guard writes what it would do with the device, sends nothing and does not
  count it as a lever. *Deutsch:* Nur beobachten je Gerät.
- **Warning for a wallbox entered twice:** a Wallbox device and an evcc loadpoint charging with nearly the same power for two minutes are
  noted once in the log (attribute `wallbox_twice`). *Deutsch:* Warnung, wenn eine Wallbox doppelt eingetragen scheint.
- Installation tests: new `tests/install/itest_evcc.py`""")])
print("ok")
