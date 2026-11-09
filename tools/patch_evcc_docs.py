"""One-off: documentation of the evcc connection (loadpoint, grid import from evcc, two-source rule) for 0.14.0 (kept for the record)."""
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


EN_GRID = """
### Grid import from evcc (since 0.14, optional)

If [evcc](https://evcc.io) runs in your house, the guard can take the grid import from it: enter the **address of evcc** in the
general settings (for example `http://192.168.1.20:7070`; with the evcc add-on of Home Assistant the IP address of your Home
Assistant and port 7070, not the sidebar address). The connection and evcc's grid meter are checked when saving.

**Rule for two sources:** the sensor you entered **always wins**. evcc is used when no sensor is entered, or as a **reserve**
(switch *evcc as a reserve for the grid import*, default on) while your sensor has no usable value (missing or older than the
maximum age). The guard changes back by itself. The two values are **never averaged**. If both are fresh and differ clearly
(more than 0.3 kW and more than 15 %) for two minutes, a note is written once to the log; the guard keeps working with your
sensor. The status sensor shows `grid_source` (`sensor` or `evcc`), `grid_evcc_kw` and `sources_differ`.
Without a grid meter in evcc (evcc only needs one for solar charging) the address is refused.
"""
DE_GRID = """
### Netzbezug aus evcc (seit 0.14, optional)

Läuft [evcc](https://evcc.io) im Haus, kann der Wächter den Netzbezug von dort nehmen: in den allgemeinen Einstellungen die **Adresse von evcc**
eintragen (zum Beispiel `http://192.168.1.20:7070`; mit dem evcc-Add-on von Home Assistant die IP-Adresse Ihres Home Assistant und Port 7070,
nicht die Adresse aus der Seitenleiste). Beim Speichern werden die Verbindung und der Netzzähler in evcc geprüft.

**Regel für zwei Quellen:** Der Sensor, den Sie eingetragen haben, **gilt immer zuerst**. evcc zählt, wenn kein Sensor eingetragen ist, oder als
**Reserve** (Schalter *evcc als Reserve für den Netzbezug*, standardmäßig an), solange Ihr Sensor nichts Brauchbares liefert (fehlt oder älter als
das Höchstalter). Der Wächter wechselt von selbst zurück. Die beiden Werte werden **nie gemittelt**. Sind beide frisch und weichen zwei Minuten lang
deutlich ab (mehr als 0,3 kW und mehr als 15 %), steht einmal ein Hinweis im Protokoll; der Wächter regelt weiter mit Ihrem Sensor. Der
Status-Sensor zeigt `grid_source` (`sensor` oder `evcc`), `grid_evcc_kw` und `sources_differ`.
Hat evcc keinen Netzzähler (evcc braucht ihn nur für das Laden mit Sonne), wird die Adresse abgelehnt.
"""
EN_LP = """### evcc loadpoint (since 0.14, experimental)

A wallbox that evcc controls can be added as device type **evcc loadpoint**: address of evcc, number of the loadpoint
(1 = first), password only if evcc asks for one. No other integration is needed. The guard sets evcc's **maximum current of the
loadpoint**, a ceiling: evcc keeps regulating below it (sun, plans, tariffs). It works with the current evcc offers right now (a
ceiling of 16 A does nothing while evcc offers 8 A) and gives back the **original** ceiling afterwards, also after a restart.
Charging is never stopped and the mode of evcc is not touched. Switching to 1 phase only if allowed and the charger can.

*Experimental:* tested against a demo evcc (0.319.0, simulated charger) in a fresh Home Assistant (installation test
`tests/install/itest_evcc.py`), not yet on real hardware. Do not enter the same wallbox a second time with its own integration.
"""
DE_LP = """### evcc-Ladepunkt (seit 0.14, experimentell)

Eine Wallbox, die evcc steuert, lässt sich als Gerätetyp **evcc-Ladepunkt** eintragen: Adresse von evcc, Nummer des Ladepunkts (1 = erster),
Passwort nur, wenn evcc eines verlangt. Eine andere Integration ist nicht nötig. Der Wächter setzt den **maximalen Ladestrom des Ladepunkts** in
evcc, eine Obergrenze: darunter regelt evcc weiter (Sonne, Pläne, Tarife). Er rechnet mit dem Strom, den evcc gerade anbietet (eine Obergrenze von
16 A bewirkt nichts, solange evcc 8 A anbietet), und gibt danach die **ursprüngliche** Obergrenze zurück, auch nach einem Neustart. Das Laden wird
nie gestoppt, der Modus von evcc bleibt unberührt. Umschalten auf 1 Phase nur, wenn erlaubt und die Wallbox es kann.

| Feld | Beispiel | Bedeutung |
|---|---|---|
| Adresse von evcc | `http://192.168.1.20:7070` | mit dem Add-on: IP von Home Assistant, Port 7070 |
| Nummer des Ladepunkts | `1` | 1 = der erste Ladepunkt in evcc |
| Passwort von evcc | | nur wenn evcc eines verlangt |
| Mindeststrom / Höchststrom | 6 / 16 A | darunter wird nie gestellt |
| Darf auf 1 Phase umschalten | aus | nur wenn die Wallbox die Phasen umschalten kann |
| Ladeleistung (optional) | | ohne sie liest der Wächter die Leistung aus evcc |

*Experimentell:* getestet gegen einen Demo-evcc (0.319.0, simulierte Wallbox) in einem frischen Home Assistant (Installationstest
`tests/install/itest_evcc.py`), noch nicht an echter Hardware. Dieselbe Wallbox nicht zusätzlich über ihre eigene Integration eintragen.

"""

edit("README.md", [
    ("4. **A template sensor you build yourself**", "4. **A template sensor you build yourself**"),
    ("### No solar plant, no inverter meter?\n", EN_GRID.lstrip("\n") + "\n### No solar plant, no inverter meter?\n"),
    ("### Wallbox compatibility\n", EN_LP + "\n### Wallbox compatibility\n"),
    ("| evcc (community) | no current number found | yes | no - regulate in evcc itself |",
     "| evcc | own device type **evcc loadpoint** (REST, no integration needed): ceiling of the loadpoint | yes | **yes, experimental** (demo evcc 0.319.0, not on hardware) |"),
])
edit("docs/ANLEITUNG.md", [
    ("### Ohne PV und ohne Wechselrichter-Zähler\n", DE_GRID.lstrip("\n") + "\n### Ohne PV und ohne Wechselrichter-Zähler\n"),
    ("### Schaltbares Gerät (aus / wieder an)\n", DE_LP + "### Schaltbares Gerät (aus / wieder an)\n"),
    ("| evcc (Community) | kein Strom als Zahl gefunden | ja | nein – in evcc selbst regeln |",
     "| evcc | eigener Gerätetyp **evcc-Ladepunkt** (REST, keine Integration nötig): Obergrenze des Ladepunkts | ja | **ja, experimentell** (Demo-evcc 0.319.0, nicht an Hardware) |"),
    ("""**Zwei Regler an einer Wallbox** (z. B. zusätzlich evcc)? Nicht gleichzeitig – die Wallbox nur in einem der
beiden eintragen.""", """**Zwei Regler an einer Wallbox** (z. B. zusätzlich evcc)? Steuert evcc die Wallbox, tragen Sie sie im Wächter als **evcc-Ladepunkt** ein,
nicht zusätzlich über ihre eigene Integration. Der Wächter setzt dann nur die Obergrenze in evcc, evcc regelt darunter."""),
])
edit("docs/COMPATIBILITY.md", [(
    "| Ohme, Blue Current (core), myenergi, evcc (community) | no current number | ❌ |",
    "| Ohme, Blue Current (core), myenergi | no current number | ❌ |\n"
    "| evcc (any wallbox evcc controls) | own device type *evcc loadpoint*: the guard sets the loadpoint's maximum current over evcc's REST API (no integration needed). "
    "Tested 2026-11-09 against a demo evcc 0.319.0 with a simulated charger, not on hardware | 🔍 experimental |",
)])
edit("docs/KOMPATIBILITAET.md", [(
    "| Ohme, Blue Current (Home Assistant), myenergi, evcc (Community) | keine Strom-Zahl | ❌ |",
    "| Ohme, Blue Current (Home Assistant), myenergi | keine Strom-Zahl | ❌ |\n"
    "| evcc (jede Wallbox, die evcc steuert) | eigener Gerätetyp *evcc-Ladepunkt*: der Wächter setzt den maximalen Ladestrom des Ladepunkts über die REST-Schnittstelle von evcc "
    "(keine Integration nötig). Getestet am 09.11.2026 gegen einen Demo-evcc 0.319.0 mit simulierter Wallbox, nicht an Hardware | 🔍 experimentell |",
)])
edit("CHANGELOG.md", [("## Unreleased\n", """## Unreleased

- **evcc loadpoint** (new device type, experimental): a wallbox that evcc controls. The guard sets the loadpoint's maximum current
  (a ceiling, evcc keeps regulating below it), works with the current evcc offers right now and gives back the original ceiling,
  also after a restart. Charging is never stopped, evcc's mode is not touched. Only the address of evcc is needed (password if evcc
  asks for one); the connection and the loadpoint are checked when saving. Tested against a demo evcc 0.319.0, not on hardware.
  *Deutsch:* neuer Gerätetyp evcc-Ladepunkt (experimentell): der Wächter setzt die Obergrenze des Ladestroms in evcc und gibt die
  ursprüngliche zurück.
- **Grid import from evcc** (optional, general settings): the entered sensor always wins; evcc is used without a sensor, or as a
  reserve (switch, default on) while the sensor has no usable value. Never averaged; a clear difference (over 0.3 kW and 15 % for
  two minutes) is noted once in the log. Attributes `grid_source`, `grid_evcc_kw`, `sources_differ` on the status sensor.
  The grid import sensor is now optional when evcc is entered. *Deutsch:* Netzbezug aus evcc, der eigene Sensor gilt zuerst,
  evcc als Reserve, nie gemittelt, Abweichungen werden gemeldet.
- Installation tests: new `tests/install/itest_evcc.py` (with a demo evcc); `itest.py` no longer runs itself when imported;
  the simulated grid sensor changes every minute so that it never counts as stale.
""")])
print("ok")
