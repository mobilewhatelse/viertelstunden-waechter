"""One-off: documentation of the guard together with a car planner (kept for the record)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def edit(rel, pairs):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, f"{rel}: {a[:70]}"
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8")


EN_TOGETHER = """- **Without a plan sensor, or when it is unavailable or its state is something else, nothing changes.**

#### The guard and a car planner together

The two have different jobs and each works on its own:

| | Peak guard (this integration) | Car planner (for example Plugwhen) |
|---|---|---|
| Question | Is the running quarter hour going above the limit? | When should the car charge so that it is ready at departure? |
| Time | every few seconds, in real time | ahead, for the whole parking time |
| Acts | throttles the wallbox, switches loads, gives everything back | plans (sun first, the rest spread at low power), warns if the car will not be ready |
| Needs | the grid import in W | state of charge, departure, wallbox power |

- **The guard always has the last word.** A plan never lifts the limit: if a peak would come anyway (cooker, oven, a car that
  starts by itself), the guard throttles as usual. It only lowers, the smaller value wins.
- **The planner learns of a throttle by itself.** It compares what really arrived with its plan and spreads the rest again; the
  guard is not changed for that and sends nothing.
- **Use one charge plan, not two.** The device type *Vehicle (charge plan)* of the guard is a simple planner for installations
  without a car planner. With a car planner chosen, switch the guard's own plan off (*Calculate the charge plan*), otherwise two
  plans that may disagree are shown (for example a fixed 80 % target against the planner's reserve-based target).
- **The dashboard follows the choice** (service *Create dashboard*, see *Dashboard*): with a car planner chosen in the general
  settings, the charge plan card shows **the planner's plan** - per vehicle the plan sensor, *Ready for departure* if the planner
  has one, the windows with energy, highest power and the share from the sun - plus the line *Car plan in the forecast*
  (connected, how many windows, until when). The guard's own plan steps back; its two switches stay below, to switch it off.
  Without a car planner the card is the guard's own plan as before.
- Both integrations stay fully usable alone: the guard without a planner, the planner without the guard (then it has no load
  forecast and plans on its own data).
"""

DE_TOGETHER = """- **Ohne Ladeplan-Sensor, oder wenn er nicht verfügbar ist oder einen anderen Zustand hat, ändert sich nichts.**

### Wächter und Auto-Planer zusammen

Beide haben verschiedene Aufgaben, und jede läuft auch allein:

| | Spitzenwächter (diese Integration) | Auto-Planer (zum Beispiel Plugwhen) |
|---|---|---|
| Frage | Geht die laufende Viertelstunde über die Grenze? | Wann soll das Auto laden, damit es zur Abfahrt bereit ist? |
| Zeit | alle paar Sekunden, in Echtzeit | im Voraus, für die ganze Standzeit |
| Tut | drosselt die Wallbox, schaltet Verbraucher, gibt alles wieder frei | plant (zuerst Sonne, der Rest mit kleiner Leistung verteilt), warnt, wenn das Auto nicht bereit sein wird |
| Braucht | den Netzbezug in W | Ladestand, Abfahrt, Wallbox-Leistung |

- **Der Wächter hat immer das letzte Wort.** Ein Plan hebt die Grenze nie auf: Käme trotzdem eine Spitze (Herd, Backrohr, ein Auto,
  das von selbst anfängt), drosselt der Wächter wie gewohnt. Er senkt nur, der kleinere Wert gilt.
- **Der Planer merkt das Drosseln selbst.** Er vergleicht, was wirklich angekommen ist, mit seinem Plan und verteilt den Rest neu; am
  Wächter wird dafür nichts geändert, er schickt nichts.
- **Einen Ladeplan verwenden, nicht zwei.** Der Gerätetyp *Fahrzeug (Ladeplan)* des Wächters ist ein einfacher Planer für Anlagen ohne
  Auto-Planer. Ist ein Auto-Planer gewählt, schalten Sie den eigenen Plan des Wächters aus (*Ladeplan berechnen*), sonst stehen zwei
  Pläne nebeneinander, die sich widersprechen können (zum Beispiel festes Ziel 80 % gegen das Reserve-Ziel des Planers).
- **Das Dashboard folgt der Wahl** (Dienst *Dashboard erstellen*, siehe 3d.): Ist in den allgemeinen Einstellungen ein Auto-Planer gewählt,
  zeigt die Ladeplan-Karte **den Plan des Planers** – je Fahrzeug den Plan-Sensor, *Bereit zur Abfahrt*, wenn der Planer einen hat, die
  Fenster mit Energie, höchster Leistung und Anteil aus der Sonne – und die Zeile *Auto-Plan in der Prognose* (verbunden, wie viele Fenster,
  bis wann). Der eigene Plan des Wächters tritt zurück; seine zwei Schalter stehen darunter, damit man ihn ausschalten kann.
  Ohne Auto-Planer ist die Karte wie bisher der eigene Plan des Wächters.
- Beide Integrationen bleiben einzeln voll nutzbar: der Wächter ohne Planer, der Planer ohne Wächter (dann ohne Lastprognose, nur mit
  seinen eigenen Daten).
"""

edit("README.md", [
    ("- **Without a plan sensor, or when it is unavailable or its state is something else, nothing changes.**\n", EN_TOGETHER),
    ("interventions per day, charge plan). Only standard cards are used.",
     "interventions per day, charge plan). Only standard cards are used. With a car planner chosen in the general settings the\n"
     "charge plan card shows the planner's plan instead of the guard's own (see *The guard and a car planner together*); create the\n"
     "dashboard again after choosing or removing a planner."),
])
edit("docs/ANLEITUNG.md", [
    ("- **Ohne Ladeplan-Sensor, oder wenn er nicht verfügbar ist oder einen anderen Zustand hat, ändert sich nichts.**\n", DE_TOGETHER),
    ("Monate, Eingriffe je Tag, Ladeplan). Es werden nur Standardkarten benutzt.",
     "Monate, Eingriffe je Tag, Ladeplan). Es werden nur Standardkarten benutzt. Ist in den allgemeinen Einstellungen ein Auto-Planer\n"
     "gewählt, zeigt die Ladeplan-Karte dessen Plan statt des eigenen (siehe *Wächter und Auto-Planer zusammen*); nach dem Wählen oder\n"
     "Entfernen eines Planers das Dashboard neu erstellen."),
])
edit("CHANGELOG.md", [
    ("- **Maximum age of the grid reading**",
     "- **Dashboard with a car planner:** when a car planner is chosen in the general settings, *Create dashboard* shows the\n"
     "  planner's charge plan (per vehicle: plan sensor, *Ready for departure* if the planner has one, windows with energy, highest\n"
     "  power and share from the sun) instead of the guard's own plan, plus the line *Car plan in the forecast* (connected, windows,\n"
     "  until when). The own plan's switches stay below so it can be switched off; one plan instead of two that disagree. Without a\n"
     "  planner the dashboard is unchanged. Planners are found by unique id (charge plan and readiness sensors of the chosen entry) or\n"
     "  taken from *Other charge plan sensors*; nothing of the planner is imported. New documentation section *The guard and a car\n"
     "  planner together* (roles, last word stays with the guard, one plan instead of two). *Deutsch:* Mit gewähltem Auto-Planer zeigt\n"
     "  das Dashboard dessen Ladeplan statt des eigenen, mit Zeile \"Auto-Plan in der Prognose\"; neuer Abschnitt \"Wächter und\n"
     "  Auto-Planer zusammen\". Ohne Planer bleibt alles wie bisher.\n"
     "- Documentation: HACS is the built-in **Marketplace** since Home Assistant 2026.11; installation texts and tables say so\n"
     "  (catalog, `hacs.json` and the validation keep their names). *Deutsch:* HACS heißt seit 2026.11 Marketplace.\n"
     "- **Maximum age of the grid reading**"),
])
print("ok")
