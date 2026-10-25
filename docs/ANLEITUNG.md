# Viertelstunden-Wächter – Anleitung

Der Wächter hält den **Mittelwert des Netzbezugs jeder Viertelstunde** unter einer Grenze. Er drosselt dafür die
Wallbox und schaltet andere Verbraucher kurz ab – nur so weit wie nötig, nach Ihren Prioritäten, und gibt alles
wieder frei, sobald Platz ist.

**Warum:** Beim Netzentgelt mit Leistungspreis (in Österreich ab 2027) zählt die höchste Viertelstunde des
Monats. Ein Abend mit Auto (11 kW) und Backrohr kann den Preis für den ganzen Monat bestimmen.

---

## 1. Was der Wächter braucht: die Messung

Zwei Sensoren in Home Assistant, egal aus welcher Integration (dafür ist **kein HACS** nötig):

| Sensor | Einheit | Pflicht | Hinweis |
|---|---|---|---|
| **Netzbezug** (Leistung) | W oder kW | ja | aktualisiert alle paar Sekunden; ein Saldo-Sensor (Einspeisung negativ) geht auch, negativ zählt als 0 |
| **Bezugszähler** (Energie) | Wh, kWh oder MWh | empfohlen | macht die Viertelstunde auch nach einem Neustart genau |

Woher die Werte kommen können – alles mit Integrationen, die in Home Assistant eingebaut sind:

| Quelle | Wie | Tempo | Für den Wächter |
|---|---|---|---|
| **Zähler des Wechselrichters** am Netzübergabepunkt (z. B. Fronius Smart Meter, SMA, Huawei, SolarEdge) | Integration des Wechselrichters, lokal | alle 1–10 s | gut |
| **Kundenschnittstelle des Netzbetreiber-Zählers** | Lesekopf mit ESPHome oder MQTT; den Schlüssel für die Schnittstelle gibt der Netzbetreiber auf Anfrage heraus | ca. 1 s | am besten |
| **Messgerät im Verteiler** (3-Phasen-Energiezähler, Hutschienenzähler) | eigene Integration oder Modbus | 1–5 s | gut |
| **Webportal des Netzbetreibers** | Portal-Integration | am nächsten Tag | **ungeeignet** (nur für Statistik) |

Beispiel: Wechselrichter mit eigenem Zähler am Netzübergabepunkt

```
Zähler am Netzübergabepunkt ──Kabel──► Wechselrichter ──LAN (lokal)──► Home Assistant
                                                                          ├─ Netzbezug (W)      → Wächter
                                                                          └─ Bezugszähler (Wh)  → Wächter
```

---

## 2. Einrichten

1. HACS → ⋮ → Benutzerdefinierte Repositories → dieses Repository, Kategorie *Integration* → herunterladen →
   Home Assistant neu starten.
2. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Viertelstunden-Wächter**:
   Netzbezug, Bezugszähler, Grenze (z. B. 10 kW), Sicherheitsabstand (z. B. 0,5 kW).
3. Geräte **auf der Integrationsseite** hinzufügen (siehe 3.): Schaltflächen **Wallbox / Schaltbares Gerät /
   Notfall-Aktion hinzufügen**. Jedes Gerät steht danach als eigener Eintrag in der Liste, mit ⋮ → **Ändern**
   oder **Löschen**. Das Zahnrad öffnet die allgemeinen Einstellungen.

Der Wächter startet in der Betriebsart **„Nur beobachten“**: Er entscheidet und schreibt mit, schaltet aber
nichts.

---

## 3. Geräte

Der Wächter kennt keine Marken, nur **Rollen**. Jedes Gerät bekommt eine **Priorität**:
**1 = wird zuerst eingeschränkt**, 10 = nur, wenn sonst nichts hilft. Zurückgegeben wird in umgekehrter
Reihenfolge.

### Wallbox (Ladestrom senken)

| Feld | Beispiel | Bedeutung |
|---|---|---|
| Ladeleistung | `sensor.wallbox_ladeleistung` | W oder kW |
| Einstellung Ladestrom | `number.wallbox_max_ladestrom` | die Zahl, mit der man den Strom setzt |
| Mindeststrom / Höchststrom | 6 / 16 A | darunter wird nie gestellt |
| Phasenwahl (optional) | `select.wallbox_phasen` | ohne sie wird nur gedrosselt |
| Option für 1 Phase | `1 Phase` | genauer Text der Auswahl |
| Genutzte Phasen (optional) | `sensor.wallbox_phasen` | |

Ablauf: 3-phasig schrittweise bis zum Mindeststrom → reicht das 2 Minuten lang nicht, auf 1 Phase umschalten
(kurze Ladepause) → zurück auf 3 Phasen erst nach 5 Minuten mit genug Luft. **Das Laden wird nie gestoppt.**
Geht, wenn die Integration der Wallbox (oder des Autos) einen einstellbaren Ladestrom anbietet. Wallboxen, die
sich nur starten und stoppen lassen, werden nicht unterstützt.

### Schaltbares Gerät (aus / wieder an)

Poolpumpe, Boiler, Heizstab, Klimaanlage, Wärmepumpe über SG-Ready-Kontakt …

| Feld | Beispiel | Bedeutung |
|---|---|---|
| Schalter | `switch.poolpumpe` | |
| Leistungssensor (optional) | `sensor.poolpumpe_leistung` | ohne Sensor gilt die angenommene Leistung |
| Läuft ab | 150 W | darunter gilt das Gerät als aus – kein Eingriff |
| Höchste Auszeit | 30 min | danach wieder an, egal was (0 = ohne Grenze) |
| Nur wieder einschalten, solange (optional) | Vorlage „darf an“ | z. B. eigener Zeitplan des Geräts |

Ein abgeschaltetes Gerät bleibt mindestens 5 Minuten aus. Wieder eingeschaltet wird nur, was der Wächter selbst
ausgeschaltet hat – und nur, wenn es noch aus ist.

### Batterie (direkt freigeben)

Für den **Hausakku** braucht es keine Skripte und keine Hilfs-Vorlagen: Der Gerätetyp **Batterie** gibt ihn im
Notfall frei, damit er das Haus versorgt und den Netzbezug senkt.

| Feld | Beispiel | Bedeutung |
|---|---|---|
| Ladestand | `sensor.akku_ladestand` | Sensor in % |
| Mindest-Ladestand | 30 % | Freigabe nur ab diesem Wert; fällt der Akku darunter, wird zurückgenommen |
| Einstellung, die die Batterie freigibt + Wert | `number.akku_max_ausgangsleistung` → `800` | eine Zahl, eine Auswahl (Option als Text, z. B. `on`) oder ein Schalter (`on`/`off`) |
| Zweite Einstellung (optional) | `select.akku_modus` → `on` | z. B. der Modus, wenn die erste Einstellung die Leistung ist |
| Erwartete Entlastung | 800 W | für Planung und Ersparnis-Schätzung |
| Höchste Dauer | 0 = ohne Grenze | danach wird auf jeden Fall zurückgenommen |
| Vorherige Werte wiederherstellen | an | stellt die Werte von vor der Freigabe wieder her – **nur die, die noch den Freigabewert haben**; hat inzwischen eine andere Automation etwas gesetzt, bleibt es |
| Skript nach dem Zurücknehmen | optional | z. B. damit Ihre eigene Automation den Akku setzt (statt Wiederherstellen, wenn der Akku eine eigene Steuerlogik hat) |

Die Batterie wird nur als Maßnahme angeboten, wenn mindestens eine ihrer Einstellungen vom Freigabewert abweicht
(sie wird nicht zweimal „freigegeben“) und der Ladestand es zulässt. Standard-Priorität ist 10: zuletzt.

### Wärmepumpen und andere Geräte mit Leistungsbegrenzung

Wärmepumpen werden in Home Assistant auf drei Arten gesteuert; der Wächter unterstützt alle drei.
**Bisher nur im Simulator getestet** (es stand keine Wärmepumpe zur Verfügung) – bitte zuerst im
Beobachtungsmodus ausprobieren.

| Ihre Wärmepumpe bietet | Gerätetyp | Beispiel |
|---|---|---|
| eine **Leistungsbegrenzung** als Zahl (Prozent, Watt, Kilowatt; oft über Modbus) | **Leistung drosseln** | Zahl „Maximale Verdichterleistung“ 100 → 30 in Schritten von 10 |
| einen **Sperrkontakt** (SG-Ready / EVU-Sperre) als ein oder zwei Schalter | **Einstellung ändern** | Sperr-Schalter → `on` (SG-Ready-Modus 1: Schalter 1 `on`, Schalter 2 `off`) |
| einen **Betriebsmodus** als Auswahl | **Einstellung ändern** | Modus-Auswahl → `Aus` oder `Eco` |
| nur einen Ein/Aus-Schalter | schaltbares Gerät | immer mit **Höchster Auszeit** |
| eine `climate`-Entität (Solltemperatur) | Notfall-Aktion (Skript) | ein Skript senkt die Solltemperatur, eines setzt sie zurück |

**Leistung drosseln:** Mit Leistungssensor wird der neue Wert aus dem echten Verbrauch berechnet (die Leistung
folgt dem Wert), ohne Sensor wird der Wert je Durchlauf um einen Schritt gesenkt. Der Wächter geht nie unter den
**niedrigsten Wert** und gibt den Wert schrittweise zurück, wenn wieder Platz ist.

**Schutz der Wärmepumpe** (alles optional, für „Leistung drosseln“ und „Einstellung ändern“):

- **Komfort-Sensor und Komfort-Minimum:** eine Raum- oder Warmwassertemperatur. Solange sie unter dem Minimum
  liegt, wird das Gerät in Ruhe gelassen, und ein laufender Eingriff wird beendet.
- **Mindestdauer:** Ein Eingriff bleibt mindestens so lange (Standard 5 Minuten).
- **Pause nach dem Zurücknehmen:** So lange warten, bevor wieder eingegriffen wird – schützt den Verdichter vor
  kurzen Zyklen (auch schaltbare Geräte haben dieses Feld).
- **Höchste Dauer:** Danach wird auf jeden Fall zurückgenommen.

**Einstellung ändern** stellt nach dem Eingriff die vorherigen Werte wieder her, aber nur die, die noch den
geänderten Wert haben (was inzwischen eine andere Automation gesetzt hat, bleibt). Hat Ihre Wärmepumpe eine
eigene Steuerlogik, schalten Sie „Vorherige Werte wiederherstellen“ aus und nutzen das Skript-Feld.

### Notfall-Aktion (Skript)

Für alles, was die anderen Gerätetypen nicht können. Beim **Hausakku** nehmen Sie besser den Gerätetyp Batterie
(oben). Das Beispiel hier zeigt das Prinzip:

Zwei kleine Skripte: eines greift ein, eines nimmt es zurück.

```yaml
# Beispiel: Akku darf voll ins Haus liefern
script:
  waechter_akku_freigeben:
    alias: "Wächter: Akku freigeben"
    sequence:
      - action: number.set_value
        target: { entity_id: number.akku_max_entladeleistung }
        data: { value: 2500 }
  waechter_akku_zurueck:
    alias: "Wächter: Akku wie vorher"
    sequence:
      - action: number.set_value
        target: { entity_id: number.akku_max_entladeleistung }
        data: { value: 800 }
```

Mit *Eingriff nur, solange* auf eine Vorlage, z. B. „Akku über 30 %“:

```
{{ states('sensor.akku_ladestand') | float(0) >= 30 }}
```

(Einstellungen → Geräte & Dienste → Helfer → Vorlage → Binärsensor.)

### Welche Aktoren gehen?

Der Wächter kann etwas **ein-/ausschalten**, einen **Strom absenken** (Wallbox) oder ein **Skript auslösen**.
Alles, was sich darauf zurückführen lässt, geht.

| Aktor | Geht? | Wie |
|---|---|---|
| Steckdosen, Relais, Pumpe, Boiler | ja | schaltbares Gerät (`switch`, `input_boolean`, `light`, `fan`) |
| Wallbox mit einstellbarem Ladestrom | ja | Wallbox (Zahl für den Strom, Phasenumschaltung optional) |
| Wärmepumpe oder Heizstab mit Kontakt (z. B. SG-Ready), Klimaanlage mit Schalter | ja | schaltbares Gerät |
| Hausakku, Wechselrichter-Modi | ja | Batterie (Einstellungen und Werte) oder Notfall-Aktion (zwei Skripte) |
| Wärmepumpe mit Leistungsbegrenzung, Sperrkontakt oder Betriebsmodus | ja (nur Simulator) | Leistung drosseln / Einstellung ändern, siehe oben |
| Alles, was in Home Assistant eine Aktion hat (Szene, Automation, Modus-Auswahl) | ja | Notfall-Aktion (Skript) |
| `climate` (Solltemperatur) | nur über Skript | ein Skript senkt die Solltemperatur, eines setzt sie zurück |
| Gerät mit **einstellbarer Leistung** (stufenloser Heizstab, Wärmepumpe in Prozent, Ladeleistung) | ja | Leistung drosseln (stufenweise) |
| Wallbox, die nur starten und stoppen kann | möglich, nicht empfohlen | als schaltbares Gerät würde sie das Laden stoppen |
| Rollläden, Beleuchtung, Schlösser | nein | sparen keine nennenswerte Leistung |

Voraussetzung: Das Gerät hat in Home Assistant einen **Zustand** (an/aus), damit der Wächter weiß, ob es
läuft. Ein Leistungssensor ist optional, sonst gilt die „angenommene Leistung“. Eingreifen darf der Wächter nur
bei dem, was Sie eingetragen haben.

### Welche Wallboxen gehen?

**Die vollständige Liste für Wallboxen, Batterien und Wärmepumpen mit dem Teststand jeder Integration (von uns getestet / Entitätstypen im Quelltext bestätigt / Hilfe gesucht): [KOMPATIBILITAET.md](KOMPATIBILITAET.md).** Für die neuen Gerätetypen ist noch nichts als „getestet“ eingetragen – Berichte sind willkommen (siehe Ende dieser Seite).

Der Wächter braucht von der Wallbox-Integration einen **Leistungssensor** und einen **einstellbaren Ladestrom**
(`number`, A). Geprüft im Quelltext der Integrationen am 25.10.2026, auf echter Hardware nur der Wattpilot.
Entitätsnamen ändern sich zwischen Versionen – bitte in der eigenen Installation nachsehen.

| Integration | Ladestrom als `number` | Leistungssensor | Geht? |
|---|---|---|---|
| Wattpilot (HACS, `wattpilot-HA`) | ja, „Max Charging Current“ | ja | **ja** (getestet, Phasenwahl vorhanden) |
| Wallbox (Home Assistant) | ja, „Maximum charging current“ | ja (kW) | **ja** (ohne Phasenumschaltung) |
| OpenEVSE (Home Assistant) | ja, „Charge rate“ (A) | ja | **ja** |
| Zaptec (HACS) | ja, „charger_max_current“ | ja (W) | **ja** |
| OCPP (HACS, `lbbrhzn/ocpp`) | ja, „Maximum Current“ | ja | **ja** (setzt ein Ladeprofil; Verhalten der Wallbox prüfen) |
| Alfen (HACS) | ja, mehrere „max current“-Zahlen | ja | **mit Vorsicht**: Geräteeinstellungen, häufiges Schreiben nicht geprüft |
| KEBA (Home Assistant) | nein, nur Dienst `keba.set_current` | ja | **über Hilfsgröße** (unten) |
| Easee (HACS) | nein, nur Dienste (z. B. Dynamic Limit) | ja | **über Hilfsgröße** (unten) |
| Ohme (Home Assistant) | nein (Zahlen sind Ziel-Prozent u. ä.) | ja | nein |
| Blue Current (Home Assistant) | nein (nur Start/Stopp) | ja | nein |
| myenergi (HACS) | nein (Mindest-Grünanteil, Prioritäten) | ja | nein |
| evcc (HACS) | kein Strom als Zahl gefunden | ja | nein – in evcc selbst regeln |
| go-e, openWB, Tesla Wall Connector, andere | nicht geprüft | | unbekannt |

**Über Hilfsgröße** (die Wallbox kennt den Strom nur über einen Dienst): einen `input_number`-Helfer anlegen
(A, Schritt 1, Ihr Minimum/Maximum) und eine Automation, die bei Änderung des Helfers den Dienst mit dem Wert
aufruft. Den Helfer trägt man als „Einstellung Ladestrom“ ein. Der Wächter ändert dann den Helfer, die Automation
gibt es weiter.

**Noch nicht gebaut (Ausblick):** Tests von „Leistung drosseln“ und „Einstellung ändern“ an echter Hardware (bisher nur im
Simulator), Akku-Reserve vor einem erwarteten Spitzenabend, früheres und sanfteres Eingreifen anhand der Prognose und
ein Tagesplan als Vorschlag einer KI-Aufgabe (gegen feste Grenzen geprüft).

---

## 3b. Lastprognose

Schalter **Lastprognose lernen und anzeigen** (standardmäßig an). Der Wächter lernt, wie hoch der Netzbezug
typischerweise je Wochentag und Viertelstunde ist: Jede fertige Viertelstunde fügt ihrem Platz einen Messwert
hinzu (der Bezug, der **ohne Wächter** entstanden wäre); je Platz bleiben die letzten 8 Werte. Pro Platz gilt:
**typisch** = Median, **hoch** = der zweithöchste Wert (bei weniger als vier Werten der höchste).
Eine Viertelstunde ist ein **Risiko**, wenn ihr „hoch“ über dem aktuellen Ziel liegt und mindestens zwei Werte
vorliegen.

Beim ersten Start wird das Modell aus den **Stundenstatistiken des Bezugszählers** gefüllt (bis zu 12 Wochen),
damit die Prognose sofort brauchbar ist. Ein Stundenmittel ist nur eine Untergrenze für seine vier Viertelstunden:
Spitzen werden anfangs unterschätzt und werden mit den laufenden Messwerten genauer. Voraussetzung: Der Zähler ist
in den allgemeinen Einstellungen eingetragen und der Recorder läuft.

Sensoren:

- **Typischer Bezug jetzt (Prognose)** – Attribute `high_kw`, `samples_here`, `samples_total`, `learned_slots`
- **Erwartete Spitze in 24 h (Prognose)** – Attribute `windows` (Risikofenster mit Beginn, Ende, `high_kw`) und
  `hours` (stündlich `typical` / `high`, für Diagramme und Karten)
- **Nächstes Spitzenrisiko** – Zeitpunkt des nächsten oder laufenden Risikofensters (Attribute `until`, `high_kw`)

Die Prognose wird bisher nur angezeigt, sie verändert nicht, was der Wächter tut. Sie ist die Grundlage für den
geplanten Ladeplan, die Akku-Reserve und das frühere Eingreifen.

---

## 3. Geräte – Anhang: Was gehört zur Integration, was stellen Sie selbst bereit?

**In der Integration** (nichts weiter zu installieren): Entscheidungslogik, Geräteliste mit Prioritäten und
Strategien, Beobachtungsmodus und Sperre, Sicherheitsregeln, alle Entitäten (Betriebsart, Strategie, Grenze,
Sicherheitsabstand, Preise, die vier Zusatz-Schalter, alle Sensoren), Kosten und Ersparnis, „bereits erreichte
Spitze nutzen“, Meldung bei Eingriff, Lastprognose, Diagnose.

**Außerhalb, in Ihrem eigenen Home Assistant** (hängt von Ihrem Haus ab, kann die Integration nicht mitbringen):

| Was | Warum | Üblicher Weg |
|---|---|---|
| Sensor für den Netzbezug (und optional der Bezugszähler) | wird von Ihrem Wechselrichter oder Zähler gemessen | Integration des Wechselrichters, ESPHome, Modbus … |
| Die Entitäten Ihrer Geräte (Ladestrom, Schalter, Leistungssensoren) | gehören zu Ihrer Hardware | die Integrationen der Geräte |
| **Optionale Bedingungs-Entitäten:** „Nur nötig, solange“, „Aktiv sperren, solange“, „Eingriff nur, solange“, „Nur wieder einschalten, solange“ | Regeln Ihres Haushalts | jede An/Aus-Entität: Vorlage-Helfer, `input_boolean`, Zeitplan. Beispiel: „Küchenstecker nur wieder einschalten, solange sein eigener Zeitplan ihn an haben will“ ist ein Vorlage-Helfer, der diesen Zeitplan liest |
| Skripte für eine Notfall-Aktion | nur für das, was die anderen Gerätetypen nicht können | zwei kleine Skripte (eingreifen / zurücknehmen); ein Hausakku braucht keine: Gerätetyp **Batterie** |
| Ein Dashboard | Geschmackssache | die Entitäten oben; die Karte zur Konfiguration steht in Abschnitt 5 |

Die Hilfs-Entitäten, die bei einer Installation wie der des Autors vorkommen („Küche darf wieder an“, „Akku-Notfall
möglich“), gehören also **nicht** zur Integration. Es sind Bedingungen und Skripte, die man für die eigenen Geräte
anlegt. Die Integration fragt nur an der Stelle danach, an der man ein Gerät einträgt.

---

## 3a. Kosten, Ersparnis und Zusatzfunktionen

Drei Schalter, **alle standardmäßig an** (nach einem Neustart gilt der letzte Stand):

| Schalter | Wirkung |
|---|---|
| **Bereits erreichte Spitze nutzen** | Abgerechnet wird die höchste Viertelstunde des Monats. Gab es in diesem Monat schon eine Spitze über der Grenze (z. B. 12 kW), kosten Viertelstunden darunter nichts mehr extra. Der Wächter arbeitet dann für den Rest des Monats mit dieser Spitze als Grenze (die Zahl „Grenze“ selbst bleibt unverändert). Das hilft nur nach einer Spitze über der Grenze; liegt die Monatsspitze unter der Grenze, ändert sich nichts. Die Monatsspitze zählt ab dem Zeitpunkt, an dem die Integration misst. |
| **Meldung bei Eingriff** | Meldung über die Benachrichtigungsdienste aus den allgemeinen Einstellungen beim ersten echten Eingriff, höchstens alle 30 Minuten. Im Beobachtungsmodus wird nichts gesendet. |
| **Kosten und Ersparnis berechnen** | Zeigt, was die Monatsspitze kostet und was sie ohne Wächter gekostet hätte. |

**Kosten erfassen:** die Zahlen **Leistungspreis bis zur Schwelle**, **Leistungspreis über der Schwelle**
(jeweils € pro kW und Jahr) und **Preisschwelle** (kW, Standard 10) – aus dem Preisblatt Ihres Netzbetreibers.
Sie stehen auf 0, solange nichts eingetragen ist (dann zeigen die Kosten-Sensoren nichts an). Die Monatsspitze
wird mit einem Zwölftel des Jahrespreises abgerechnet; der Teil bis zur Schwelle mit dem ersten Preis, der Teil
darüber mit dem zweiten:

```
Kosten = ( min(Spitze, Schwelle) × Preis_niedrig + max(Spitze − Schwelle, 0) × Preis_hoch ) / 12
```

Beispiel: 13,1 kW ohne Wächter, 9,4 kW mit Wächter, Preise 33,82 und 67,64 €/kW/Jahr: 45,66 € statt 26,49 €
im Monat, gespart **19,16 €**.

Sensoren: **Leistungspreis diesen Monat**, **… ohne Wächter (Schätzung)**, **Ersparnis diesen Monat / dieses Jahr
(Schätzung)** (Attribut `months`), **Entlastung jetzt (Schätzung)**.

**Wie die Ersparnis geschätzt wird** (nur im Modus „Aktiv“; beim Beobachten wird nichts „gespart“): Der Wächter
rechnet je Viertelstunde zusammen, was seine Eingriffe aus dem Netzbezug herausgehalten haben – Wallbox: was ihre
Einstellung beim ursprünglichen Strom erlaubt hätte minus dem, was sie jetzt ziehen kann (nie weniger als das, was
sie wirklich zieht); schaltbares Gerät: die Leistung, die es beim Ausschalten hatte, solange es aus ist;
Notfall-Aktion: die eingetragene erwartete Entlastung. Die höchste dieser „ungeschützten“ Viertelstunden des
Monats wird nach dem Tarif bepreist. Das ist eine Schätzung, keine Messung.

---

## 3c. Ladeplan fürs Auto

Gerätetyp **Fahrzeug (Ladeplan)**. Er plant, in welchen Viertelstunden das Auto laden soll, damit es bis zur nächsten
Abfahrt sein Ziel erreicht, und zeigt den Plan an. **Das Ausführen ist ein eigener Schalter, standardmäßig aus.**

**Was Sie eintragen:** Ladestand des Autos (Sensor, %), Ziel (fester Prozentwert, optional aus einem Sensor wie dem
Ladelimit des Autos), Batteriekapazität (kWh), nächste Abfahrt (eine *Uhrzeit*-Entität – genommen wird das nächste
Auftreten – oder eine Datum-Uhrzeit-Entität / `input_datetime` / Zeitstempel-Sensor), höchste und niedrigste
Ladeleistung der Wallbox, Grundlast des Hauses, optional eine Entität „Auto angesteckt“ und optional die Befehle zum
**Erlauben** und **Pausieren** des Ladens (Knopf, Schalter, Auswahl oder Zahl).

**So plant er** (`plan.py`, mit Tests):

1. Benötigte Energie = (Ziel − Ladestand) × Kapazität / 0,9 (Ladeverluste).
2. **Zuerst die Sonne:** Gibt es eine Solarprognose, werden Viertelstunden mit PV-Überschuss (Prognose minus
   Grundlast des Hauses, mindestens die niedrigste Ladeleistung) zuerst gefüllt – Laden mit Sonne kostet keine
   Netzenergie.
3. **Dann die ruhigsten Viertelstunden:** Der gelernte erwartete Netzbezug (der „hoch“-Wert der Lastprognose)
   entscheidet; eine Viertelstunde wird nur so weit genutzt, dass *erwarteter Bezug + was das Auto aus dem Netz zieht*
   unter dem Spitzenziel bleibt.
4. Schafft das Auto sein Ziel bis zur Abfahrt nicht, steht der Zustand auf **Ziel nicht erreichbar**, und die fehlenden
   kWh werden angezeigt. Der Plan tut nie so, als ginge es.

**Die Solarprognose ist optional und kommt aus dem Energie-Dashboard.** Der Plan benutzt die Solarprognose, die dort
eingerichtet ist (Einstellungen > Dashboards > Energie > Solarmodule > *Prognose*; Integrationen mit Prognose sind
z. B. Forecast.Solar und Solcast). **Ohne sie funktioniert der Plan trotzdem**, rechnet aber nur mit dem erwarteten
Netzbezug, und der Sensor zeigt einen Hinweis (`solar_used: false`). Die Stundenprognose wird auf ihre vier
Viertelstunden verteilt.

**Ausführen** (Schalter *Ladeplan auch ausführen*, **standardmäßig aus und nach jedem Neustart wieder aus**): Außerhalb
der geplanten Zeiten wird der *Pausieren*-Befehl gesendet, innerhalb der *Erlauben*-Befehl. Dafür braucht es einen
Pausieren-Befehl (ohne ihn bleibt der Plan ein Vorschlag). Schutzregeln:

- nur solange der Plan das Ziel erreichen kann (Zustand *Geplant*) und das Auto angesteckt ist (wenn Sie diese
  Entität eingetragen haben);
- ist der Plan nicht machbar, nicht nötig, ohne Abfahrt, wird der Schalter ausgeschaltet, die Integration entladen oder
  Home Assistant neu gestartet, wird der *Erlauben*-Befehl gesendet, damit das Auto normal lädt;
- höchstens ein Befehl alle fünf Minuten, solange der Plan läuft; das Freigeben wird nie verzögert;
- der Spitzenwächter arbeitet zusätzlich weiter und stoppt das Auto, wie immer, nie von sich aus.

**Grenzen:** Es wird nur der erste Fahrzeug-Eintrag benutzt; der Plan ist ein Vorschlag aus Gewohnheiten (Lastprognose)
und einer Prognose, keine Garantie; das Auto kann sich anders verhalten (es kann eine Ladung von selbst beenden); er
wurde **noch nicht an echter Hardware ausprobiert** – starten Sie mit dem Schalter aus und vergleichen Sie den Plan
mit dem, was Sie selbst tun würden.

Sensor **Ladeplan** (Zustände: Aus, Kein Fahrzeug eingerichtet, Ladestand fehlt, Keine Abfahrtszeit, Nicht nötig,
Geplant, Ziel nicht erreichbar) mit den Attributen `windows`, `text`, `needed_kwh`, `planned_kwh`, `solar_kwh`,
`grid_kwh`, `shortfall_kwh`, `ready_at`, `latest_start`, `departure`, `soc`, `target_soc`, `solar_used`,
`paused_by_plan`, `hint`.

---

## 3d. Fertiges Dashboard

Der Dienst **Dashboard erstellen** (`viertelstunden_waechter.create_dashboard`) baut ein fertiges Dashboard mit den
Entitäten **Ihrer** Installation (egal wie das Gerät heißt, auf Deutsch oder Englisch): die Übersicht (Einstellungen,
Zusatzfunktionen, Geräte und Prioritäten, Jetzt, Kosten und Ersparnis) und *Statistik und Prognose* (24-Stunden-Vorschau
als Balken, Wochenprofil, Spitzen der letzten Tage, Monate, Eingriffe je Tag, Ladeplan). Es werden nur Standardkarten
benutzt.

- Mit einer Dashboard-Adresse (z. B. `waechter`): zuerst ein leeres Dashboard anlegen (Einstellungen > Dashboards >
  Hinzufügen), dann den Dienst mit dessen Adresse aufrufen – die Ansichten dort werden ersetzt.
- Ohne Adresse: Das YAML wird zurückgegeben und als Benachrichtigung angezeigt; in ein neues Dashboard einfügen
  (drei Punkte > Bearbeiten > Rohkonfigurations-Editor). Das ist der robustere Weg, falls sich in Home Assistant intern
  etwas ändert.

---

## 4. Allgemeine Einstellungen

| Einstellung | Wozu |
|---|---|
| **Nur nötig, solange** | Der Wächter greift nur ein, solange diese Entität an ist. Leer lassen = immer wachsam (empfohlen). |
| **„Aktiv“ sperren, solange** | Läuft noch ein alter Wächter oder eine Automation, die dieselben Geräte steuert: „Aktiv“ wird verweigert. |
| **Benachrichtigungsdienste** | z. B. `notify.mobile_app_handy` – Meldung, wenn die Grenze trotz aller Hebel nicht zu halten ist |
| **Betriebsart nach Neustart** | Wiederherstellen / Beobachten / Aktiv / Aus |

Sofort änderbar (Gerät des Wächters oder Dashboard): **Betriebsart**, **Strategie**, **Grenze**,
**Sicherheitsabstand**.

### Strategie

- **Strenge Reihenfolge:** wie eine feste Liste – erst Priorität 1 bis zum Ende, dann 2, …
- **Geringster Komfortverlust:** die günstigste Kombination (Summe der Prioritäten), die reicht.
  Beispiel: 0,7 kW zu viel, Pool hat Priorität 1, Wallbox 3 → nur der Pool geht aus, das Auto lädt weiter.

---

## 5. Was ist eingestellt? – Übersicht

- Die **Integrationsseite** listet alle Geräte (ändern und löschen dort); das Zahnrad enthält die allgemeinen
  Einstellungen.
- ⋮ → **Diagnose herunterladen**: Konfiguration, aktuelle Werte, Eingriffe, Protokoll.
- Dashboard-Karte (Markdown):

```
{% set c = state_attr('sensor.viertelstunden_wachter_status', 'configuration') %}
{% macro n(e) %}{% set s = states[e] if e else none %}{{ s.name if s else (e or '–') }}{% endmacro %}
{% if c %}**Messung:** {{ n(c.get('grid_power')) }} · {{ n(c.get('grid_energy')) }}

| Prio | Gerät | Steuert |
|---:|---|---|
{% for d in c.get('devices', []) %}| {{ d.get('priority') }} | {{ d.get('name') }} | {{ n(d.get('current_entity') or d.get('switch_entity') or d.get('on_script')) }} |
{% endfor %}{% endif %}
```

Dashboards rendern Vorlagen streng: fehlende Felder mit `.get('…')` abfragen, nicht mit `d.feld`.

Protokoll des Tages: Attribut `today` des Status-Sensors. Spitzen der letzten 31 Tage: Attribut `days` von
„Spitze heute“.

---

## 6. Vom Beobachten zum Eingreifen

1. Ein paar Abende **„Nur beobachten“**, an denen wirklich viel läuft (Auto lädt aus dem Netz, gekocht wird).
   Im Protokoll stehen die Entscheidungen mit „(beobachtet)“.
2. Passt das, den alten Wächter bzw. die alte Automation ausschalten.
3. Betriebsart **„Aktiv“**, einen Abend zusehen.
4. Zurück jederzeit: **„Nur beobachten“** oder **„Aus“** – alles, was der Wächter verändert hat, wird sofort
   zurückgegeben.

Hinweis: Im Beobachtungsmodus sieht der Wächter den Netzbezug, *nachdem* ein anderer Regler schon eingegriffen
hat. Er braucht dann oft weniger zu tun – wichtig sind Abweichungen in Reihenfolge und Zeitpunkt.

---

## 7. Sicherheit

- Messwerte fehlen 90 s, Wächter aus, Neustart von Home Assistant, Integration entladen → alles wird
  freigegeben.
- Höchste Auszeit je Gerät wird immer eingehalten.
- Unplausible Zählersprünge (nach einem Ausfall) werden verworfen.
- Entscheidungen nach Mittelwerten (Herd und Wasserkocher takten): Abschalten nach dem 1-Minuten-Mittel,
  Zurückgeben erst, wenn 2 Minuten lang genug Luft war.
- Der Wächter ersetzt **nicht** die Absicherung im Verteiler und kein vorgeschriebenes Lastmanagement.

---

## 8. Häufige Fragen

**Nur das Auto?** Nein – überwacht wird der gesamte Netzbezug. Eingreifen kann er bei allen eingetragenen
Geräten.

**Was, wenn alle Hebel nicht reichen?** Gegen Ende der Viertelstunde eine Benachrichtigung (falls eingetragen).
Die Viertelstunde liegt dann über der Grenze.

**Zwei Regler an einer Wallbox** (z. B. zusätzlich evcc)? Nicht gleichzeitig – die Wallbox nur in einem der
beiden eintragen.

**Braucht der Wächter Internet oder KI?** Nein. Alles läuft lokal.
