# Viertelstunden-Wächter – Anleitung

Der Wächter hält den **Mittelwert des Netzbezugs jeder Viertelstunde** unter einer Grenze. Er drosselt dafür die
Wallbox und schaltet andere Verbraucher kurz ab – nur so weit wie nötig, nach Ihren Prioritäten, und gibt alles
wieder frei, sobald Platz ist.

**Warum:** Beim Netzentgelt mit Leistungspreis (in Österreich ab 2027) zählt die höchste Viertelstunde des
Monats. Ein Abend mit Auto (11 kW) und Backrohr kann den Preis für den ganzen Monat bestimmen.

---

## 1. Was der Wächter braucht: die Messung

**Wie frisch muss der Messwert sein?** Der Wächter hält die *laufende* Viertelstunde unter der Grenze, braucht also alle paar Sekunden einen
neuen Wert (alle 10 bis 30 s ist gut). Ein Sensor, der nur alle 15 Minuten oder stündlich aktualisiert, taugt nicht zum Regeln: Der Wächter
sähe die Viertelstunde erst, wenn sie vorbei ist. Deshalb gilt ein Messwert, der länger als das **Höchstalter** (Einstellung, Standard
2 Minuten, 0 = aus) nicht geschrieben wurde, als fehlend: kein Eingriff, nach 90 Sekunden wird alles zurückgegeben, Status *keine Daten*.
Die Attribute `grid_age_s` und `grid_stale` des Status-Sensors zeigen es an. Ohne schnellen Zähler zeigt der Wächter Spitzen, Kosten und
Prognose im Nachhinein (Beobachtungsmodus); für das Steuern des Ladens nehmen Sie dann den Auto-Planer.

Zwei Sensoren in Home Assistant, egal aus welcher Integration (dafür ist **nichts aus dem Marketplace** nötig):

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
| **Selbst gebauter Template-Sensor**, z. B. aus den drei Phasenwerten eines **Shelly 3EM Pro** (Summe der Phasen, der positive Teil als Bezug) | Template in der Konfiguration; jeder Sensor mit der Einheit W oder kW geht, **eine Geräteklasse ist nicht nötig** (geprüft wird die Einheit) | wie der Shelly | gut; im Installationstest mit einem gleichwertigen simulierten Sensor abgedeckt, mit einem echten Shelly hier nicht getestet |
| **Webportal des Netzbetreibers** | Portal-Integration | am nächsten Tag | **ungeeignet** (nur für Statistik) |

Beispiel: Wechselrichter mit eigenem Zähler am Netzübergabepunkt

```
Zähler am Netzübergabepunkt ──Kabel──► Wechselrichter ──LAN (lokal)──► Home Assistant
                                                                          ├─ Netzbezug (W)      → Wächter
                                                                          └─ Bezugszähler (Wh)  → Wächter
```

### Netzbezug aus evcc (seit 0.14, optional)

Läuft [evcc](https://evcc.io) im Haus, kann der Wächter den Netzbezug von dort nehmen: in den allgemeinen Einstellungen die **Adresse von evcc**
eintragen (zum Beispiel `http://192.168.1.20:7070`; mit dem evcc-Add-on von Home Assistant die IP-Adresse Ihres Home Assistant und Port 7070,
nicht die Adresse aus der Seitenleiste). Beim Speichern werden die Verbindung und der Netzzähler in evcc geprüft.

**Regel für zwei Quellen:** Der Sensor, den Sie eingetragen haben, **gilt immer zuerst**. evcc zählt, wenn kein Sensor eingetragen ist, oder als
**Reserve** (Schalter *evcc als Reserve für den Netzbezug*, standardmäßig an), solange Ihr Sensor nichts Brauchbares liefert (fehlt oder älter als
das Höchstalter). Der Wächter wechselt von selbst zurück. Die beiden Werte werden **nie gemittelt**. Sind beide frisch und weicht der Bezug zwei Minuten lang
deutlich ab (mehr als 0,3 kW und mehr als 15 %; Einspeisung zählt auf beiden Seiten als 0), steht einmal ein Hinweis im Protokoll; der Wächter regelt weiter mit Ihrem Sensor. Der
Status-Sensor zeigt `grid_source` (`sensor` oder `evcc`), `grid_evcc_kw` und `sources_differ`.
Hat evcc keinen Netzzähler (evcc braucht ihn nur für das Laden mit Sonne), wird die Adresse abgelehnt.
Mit evcc-Adresse hat das erzeugte Dashboard eine kleine Karte **Quellen im Vergleich**: beide Werte als Balken, welcher gerade gilt, und
eine Warnzeile, wenn sie abweichen oder eine Wallbox doppelt eingetragen scheint. Ohne evcc gibt es die Karte nicht.

### Ohne PV und ohne Wechselrichter-Zähler

Der Wächter braucht **keine PV-Anlage**. Er braucht nur den Netzbezug in Watt; die Sonne nutzt nur der optionale Ladeplan.
Wer nur den Zähler des Netzbetreibers hat (in Österreich der Smart Meter des *Netzbetreibers*, nicht des Stromlieferanten,
zum Beispiel Netz Burgenland bei Kunden von Energie Burgenland), hat zwei Wege:

- **Einfachster Start: ein eigener Zähler im Verteiler.** Ein 3-Phasen-Energiezähler mit Klemmen oder für die Hutschiene (zum
  Beispiel ein Shelly Pro 3EM oder Shelly EM mit Stromwandlern; die Integration ist in Home Assistant eingebaut) liefert den Bezug etwa
  jede Sekunde. Dafür braucht man nichts vom Netzbetreiber.
- **Beste Quelle: die Kundenschnittstelle des Smart Meters.** Der Netzbetreiber muss die Schnittstelle freischalten und den Schlüssel
  herausgeben; bitte dort anfragen (Formular oder E-Mail, der Weg hängt vom Netzbetreiber ab, in Österreich ist es kostenlos). Danach liest
  ein Lesekopf mit ESPHome oder MQTT die Werte. Ein Beispiel für das Netz Burgenland und den Landis+Gyr E450 ist
  [smartmeter_homeassistant_burgenland](https://github.com/r00tat/smartmeter_homeassistant_burgenland), ein allgemeines Lesekopf-Projekt
  [esp-smartmeter-reader](https://github.com/aldadic/esp-smartmeter-reader), die Adapter-Spezifikation
  [von Österreichs Energie](https://oesterreichsenergie.at/fileadmin/user_upload/Datenblatt_Smart_Meter_Adapter_V7_20220808__2_.pdf).
  Vom Autor nicht getestet; wie oft der Zähler einen Wert liefert, hängt vom Zählertyp ab.

In beiden Fällen arbeitet der Wächter mit dem Netzbezug in W oder kW und, wenn vorhanden, dem Bezugszähler (siehe Tabelle oben).

---

## 2. Einrichten

1. **Einstellungen → Marketplace** öffnen (bis Home Assistant 2026.10 hieß das HACS), nach **Viertelstunden-Wächter** suchen, herunterladen →
   Home Assistant neu starten. (Wird es im Marketplace noch nicht gefunden, weil der Antrag für die Standardliste noch läuft,
   einmalig als Benutzerdefiniertes Repository hinzufügen: Marketplace → ⋮ → Benutzerdefinierte Repositories → dieses
   Repository, Kategorie *Integration*.)
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

### evcc-Ladepunkt (seit 0.14, experimentell)

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

**Nur beobachten (jedes Gerät, seit 0.14):** ein Schalter in jedem Gerät. Der Wächter schreibt dann nur ins Protokoll, was er mit diesem Gerät
tun würde (*Nur beobachten: Wallbox würde um 3,6 kW gesenkt …*, höchstens einmal je Viertelstunde), sendet nichts und zählt das Gerät nicht als
Hebel, weicht also deshalb auch nicht auf andere Geräte aus. Gut, um ein neues Gerät (zum Beispiel einen evcc-Ladepunkt) neben dem laufenden
Wächter auszuprobieren.

**Eine Wallbox doppelt eingetragen:** Laden ein Gerät *Wallbox* und ein *evcc-Ladepunkt* zwei Minuten lang gleichzeitig mit fast gleicher Leistung
(höchstens 15 % Unterschied, über 1 kW), schreibt der Wächter einmal ins Protokoll, dass es vermutlich dieselbe Wallbox ist, und zeigt es im
Attribut `wallbox_twice` des Status-Sensors. Er ändert nichts; die Wallbox nur einmal eintragen (als evcc-Ladepunkt, wenn evcc sie steuert).

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
| Wattpilot (Community, `wattpilot-HA`) | ja, „Max Charging Current“ | ja | **ja** (getestet, Phasenwahl vorhanden) |
| Wallbox (Home Assistant) | ja, „Maximum charging current“ | ja (kW) | **ja** (ohne Phasenumschaltung) |
| OpenEVSE (Home Assistant) | ja, „Charge rate“ (A) | ja | **ja** |
| Zaptec (Community) | ja, „charger_max_current“ | ja (W) | **ja** |
| OCPP (Community, `lbbrhzn/ocpp`) | ja, „Maximum Current“ | ja | **ja** (setzt ein Ladeprofil; Verhalten der Wallbox prüfen) |
| Alfen (Community) | ja, mehrere „max current“-Zahlen | ja | **mit Vorsicht**: Geräteeinstellungen, häufiges Schreiben nicht geprüft |
| KEBA (Home Assistant) | nein, nur Dienst `keba.set_current` | ja | **über Hilfsgröße** (unten) |
| Easee (Community) | nein, nur Dienste (z. B. Dynamic Limit) | ja | **über Hilfsgröße** (unten) |
| Ohme (Home Assistant) | nein (Zahlen sind Ziel-Prozent u. ä.) | ja | nein |
| Blue Current (Home Assistant) | nein (nur Start/Stopp) | ja | nein |
| myenergi (Community) | nein (Mindest-Grünanteil, Prioritäten) | ja | nein |
| evcc | eigener Gerätetyp **evcc-Ladepunkt** (REST, keine Integration nötig): Obergrenze des Ladepunkts | ja | **ja, experimentell** (Demo-evcc 0.319.0, nicht an Hardware) |
| go-e Charger (Community, `marq24/ha-goecharger-api2`) | ja, Zahl in A (6-32 A); Phasenmodus `psm` als Auswahl | ja | **ja** (im Quellcode geprüft, nicht an Hardware getestet; Gemini flex ist ausdrücklich genannt) |
| openWB, Tesla Wall Connector, andere | nicht geprüft | | unbekannt |

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

Die Prognose wird angezeigt und speist den Ladeplan (3c). Das Verhalten des Wächters ändert sie nur, wenn Sie den Schalter
**Vorausschauend drosseln nach Prognose** einschalten (siehe unten).

### Wetterkorrektur (seit 0.14, Schalter **Wetterkorrektur der Prognose**, standardmäßig an)

Heizen im Winter und die Klimaanlage im Sommer verändern die Last; das reine Wochenmuster ist an einem kalten oder heißen Tag zu
niedrig. In den allgemeinen Einstellungen wählen Sie eine **Wetter-Entität** (Vorhersage der Außentemperatur) und optional einen
**Außentemperatur-Sensor**. Ohne beides ändert sich nichts.

- Jeder gelernte Wert merkt sich die Außentemperatur dieser Zeit.
- Aus ganzen Tagen (Hauslast gegen mittlere Temperatur, nachdem die Wochentagsgewohnheit abgezogen ist) bestimmt der Wächter zwei
  Steigungen: zusätzliche kW je Kelvin **unter 15 °C** (Heizen) und **über 22 °C** (Kühlen). Eine Steigung wird nur bestimmt, wenn die
  Tage wirklich kaltes oder heißes Wetter zeigen, sie ist nie negativ und braucht mindestens 14 Tage. Bis dahin gilt die bisherige Prognose.
- Für eine Viertelstunde der Prognose wird jeder Wert auf die erwartete Temperatur umgerechnet (Stundenvorhersage der Wetter-Entität,
  sonst der Tagesmittelwert). Werte ohne Temperatur bleiben unverändert.
- Mit einem Außentemperatur-Sensor mit Langzeitstatistik werden die Temperaturen der letzten 12 Wochen einmal gelesen, die Korrektur
  kann sofort beginnen; ohne ihn lernt der Wächter die Temperatur ab jetzt (etwa zwei Wochen).
- Das Attribut `weather` von **Typischer Bezug jetzt (Prognose)** zeigt, was gelernt ist: Steigungen, verwendete Tage, Güte (`r2`).

Grenzen: Das Modell beschreibt den **Netzbezug**. An einem sonnigen Tag senkt die Solaranlage den Bezug; ein heißer, sonniger Tag kann
daher weniger Kühllast zeigen als ein heißer, bewölkter. Die Solarprognose als weiterer Eingang ist geplant. Die Korrektur ist ein
Tagesmittel, kein Tagesverlauf der Heizung. Mit Wallbox bleibt das Auto aus der Berechnung (Haus ohne Wallbox), sobald der Wächter
es live misst; der erste Import aus der Statistik enthält das Auto noch.

### Ladeplan eines Auto-Planers (optional)

In den allgemeinen Einstellungen wählen Sie einfach **den Auto-Planer** aus (zum Beispiel *Plugwhen*; er wird vorgeschlagen, wenn genau einer
installiert ist): Der Wächter findet dann die Ladepläne aller seiner Fahrzeuge selbst, auch später hinzugefügte. Einen anderen Planer
binden Sie über das Feld *Andere Ladeplan-Sensoren* an. Ein Ladeplan-Sensor braucht die Attribute `windows` (Beginn, Ende, `energy_kwh`,
`peak_kw`) und `departure` sowie den Zustand `planned`, `not_needed` oder `infeasible`.

- Bis zur Abfahrt ist die Prognose das Haus allein **plus das, was der Plan für das Auto in dieser Viertelstunde vorsieht** (Durchschnitt für
  *typisch*, Spitze für *hoch*). Das gelernte Wallbox-Muster zählt dort nicht: Der Plan weiß besser, wann das Auto wirklich lädt.
- Ein Plan ohne Fenster (*nicht nötig*) heißt: keine Auto-Last bis zur Abfahrt. Nach der Abfahrt gilt wieder die übliche Sicht.
- Mehrere Autos addieren sich. Das Attribut `car_plan` von **Typischer Bezug jetzt (Prognose)** zeigt, ob ein Plan benutzt wird.
- **Ohne Ladeplan-Sensor, oder wenn er nicht verfügbar ist oder einen anderen Zustand hat, ändert sich nichts.**

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
  bis wann). **Entweder der Planer oder der Wächter:** Mit Auto-Planer steht der eigene Plan des Wächters mit seinen zwei Schaltern gar nicht
  im Dashboard (er bleibt auf der Geräteseite; dort *Ladeplan berechnen* ausschalten).
  Ohne Auto-Planer ist die Karte wie bisher der eigene Plan des Wächters.
- Beide Integrationen bleiben einzeln voll nutzbar: der Wächter ohne Planer, der Planer ohne Wächter (dann ohne Lastprognose, nur mit
  seinen eigenen Daten).


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
| **Optionale Bedingungs-Entitäten:** „Nur nötig, solange“, „Aktiv sperren, solange“, „Eingriff nur, solange“, „Nur wieder einschalten, solange“ | Regeln Ihres Haushalts | jede An/Aus-Entität: Vorlage-Helfer, `input_boolean`, Zeitplan. Beispiel: „Gerät nur wieder einschalten, solange sein eigener Zeitplan es an haben will“ ist ein Vorlage-Helfer, der diesen Zeitplan liest |
| Skripte für eine Notfall-Aktion | nur für das, was die anderen Gerätetypen nicht können | zwei kleine Skripte (eingreifen / zurücknehmen); ein Hausakku braucht keine: Gerätetyp **Batterie** |
| Ein Dashboard | Geschmackssache | die Entitäten oben; die Karte zur Konfiguration steht in Abschnitt 5 |

Hilfs-Entitäten wie „Gerät darf wieder an“ (ein Vorlage-Helfer, der einen Zeitplan liest) oder „Notfall möglich“
gehören also **nicht** zur Integration. Es sind Bedingungen und Skripte, die man für die eigenen Geräte
anlegt. Die Integration fragt nur an der Stelle danach, an der man ein Gerät einträgt.

---

## 3a. Kosten, Ersparnis und Zusatzfunktionen

Drei Schalter, **alle standardmäßig an** (nach einem Neustart gilt der letzte Stand):

| Schalter | Wirkung |
|---|---|
| **Bereits erreichte Spitze nutzen** | Abgerechnet wird die höchste Viertelstunde des Monats. Gab es in diesem Monat schon eine Spitze über der Grenze (z. B. 12 kW), kosten Viertelstunden darunter nichts mehr extra. Der Wächter arbeitet dann für den Rest des Monats mit dieser Spitze als Grenze (die Zahl „Grenze“ selbst bleibt unverändert). Das hilft nur nach einer Spitze über der Grenze; liegt die Monatsspitze unter der Grenze, ändert sich nichts. Die Monatsspitze zählt ab dem Zeitpunkt, an dem die Integration misst. |
| **Meldung bei Eingriff** | Meldung über die Benachrichtigungsdienste aus den allgemeinen Einstellungen: (1) beim ersten echten Eingriff mit **allem, was der Wächter in diesem Schritt getan hat** (z. B. „Wallbox 16 A -> 12 A (3-phasig, 1.6 kW zu viel)“), höchstens alle 30 Minuten; (2) wenn alles wieder freigegeben ist, eine **Zusammenfassung aller Schritte** mit Uhrzeiten (bis zu 15 Zeilen). Im Beobachtungsmodus wird nichts gesendet. |
| **Kosten und Ersparnis berechnen** | Zeigt, was die Monatsspitze kostet und was sie ohne Wächter gekostet hätte. |

**Kosten erfassen:** die Zahlen **Leistungspreis bis zur Schwelle**, **Leistungspreis über der Schwelle**
(jeweils € pro kW und Jahr) und **Preisschwelle** (kW, Standard 10) – aus dem Preisblatt Ihres Netzbetreibers.
Sie stehen auf 0, solange nichts eingetragen ist (dann zeigen die Kosten-Sensoren nichts an). Die Monatsspitze
wird mit einem Zwölftel des Jahrespreises abgerechnet; der Teil bis zur Schwelle mit dem ersten Preis, der Teil
darüber mit dem zweiten:

```
Kosten = ( min(Spitze, Schwelle) × Preis_niedrig + max(Spitze − Schwelle, 0) × Preis_hoch ) / 12
```

Beispiel: 13,1 kW ohne Wächter, 9,4 kW mit Wächter, Preise 30 und 60 pro kW und Jahr: 40,50 statt 23,50
im Monat, gespart **17,00**.

Sensoren: **Leistungspreis diesen Monat**, **… ohne Wächter (Schätzung)**, **Ersparnis diesen Monat / dieses Jahr
(Schätzung)** (Attribut `months`), **Entlastung jetzt (Schätzung)**.

**Wie die Ersparnis geschätzt wird** (nur im Modus „Aktiv“; beim Beobachten wird nichts „gespart“): Der Wächter
rechnet je Viertelstunde zusammen, was seine Eingriffe aus dem Netzbezug herausgehalten haben – Wallbox: was ihre
Einstellung beim ursprünglichen Strom erlaubt hätte minus dem, was sie jetzt ziehen kann (nie weniger als das, was
sie wirklich zieht); schaltbares Gerät: die Leistung, die es beim Ausschalten hatte, solange es aus ist;
Notfall-Aktion: die eingetragene erwartete Entlastung. Die höchste dieser „ungeschützten“ Viertelstunden des
Monats wird nach dem Tarif bepreist. Das ist eine Schätzung, keine Messung.

---

### Vorausschauend drosseln nach Prognose (Schalter, Standard aus)

Normalerweise reagiert der Wächter, wenn die laufende Viertelstunde über das Ziel läuft. Mit dem Schalter **Vorausschauend drosseln
nach Prognose** nutzt er zusätzlich das gelernte Muster des Wochentags: In einer **Risiko-Viertelstunde** (die Prognose `high` liegt
über dem Ziel, mindestens 3 Messwerte) hält er eine **Reserve** frei: die übliche Spitze über dem typischen Wert (`high - typisch`,
höchstens 3 kW, unter 0,5 kW ignoriert). Er handelt dann, als läge das Ziel um diese Reserve niedriger – aber nur mit den **sanften**
Hebeln:

- der **Ladestrom der Wallbox** wird gesenkt (nie auf 0, nie unter Ihr Minimum),
- **Drosseln** (z. B. Wärmepumpe in Prozent) werden schrittweise gesenkt,
- wegen einer Prognose wird **kein Gerät ausgeschaltet** und **nicht auf 1 Phase umgeschaltet** (das unterbricht das Laden); das bleibt
  dem echten Überschreiten vorbehalten.

Zurückgeben läuft umgekehrt: Ist die Risiko-Viertelstunde vorbei, ist die Reserve 0 und die übliche stufenweise Rückgabe folgt. Die
Protokollzeilen beginnen mit „Vorausschauend (laut Prognose Spitzen bis … kW, typisch … kW):“, man sieht also den Grund; das Attribut
`forecast_reserve_kw` des Status zeigt die Reserve der laufenden Viertelstunde. Voraussetzung: *Lastprognose lernen und anzeigen* (an) und
genug Messwerte – der Verlaufsimport füllt das Profil zuerst mit Stundenmitteln (Spitzen werden unterschätzt), die echten Viertelstunden
machen es in einigen Wochen genau. Im **Beobachtungsmodus** wird nur protokolliert, was er tun würde. Empfehlung: nach ein paar Tagen
einschalten, wenn das Wochenprofil stimmig aussieht.

### Sprache

Alles folgt der Sprache von Home Assistant: Deutsch bei deutschen Installationen, Englisch bei jeder anderen Sprache. Das gilt
für Einrichtungsdialoge, Entitätsnamen, Dienste, Dashboard, Wochenbericht, KI-Erklärer und (seit 0.13) auch für die Protokollzeilen und
Meldungen des Wächters („Wallbox 16 A -> 12 A (3-phasig, 1.7 kW zu viel)“). Zeilen, die schon im Protokoll stehen, bleiben in ihrer Sprache.

### Haus und Auto getrennt, Akku-Reserve, Export, KI-Erklärer (0.13)

**Haus und Auto getrennt (automatisch).** Mit einem Wallbox-Eintrag lernt der Wächter aus denselben Viertelstunden zwei Muster: das Haus ohne
Wallbox (gemessener Bezug minus Wallbox-Leistung) und die Wallbox allein. Die Prognose zählt normalerweise beides zusammen. Sagt ein
Fahrzeug-Eintrag, dass das Auto **voll** ist (Ladestand am Ziel) oder **nicht angesteckt** (die optionale Entität *verbunden* ist aus), und
lädt die Wallbox nicht, rechnet die Prognose ohne Auto: Das übliche Laden am Abend ist dann kein Risikofenster, *Vorausschauend drosseln* hält
dafür keine Reserve und die *Akku-Reserve* hält den Akku nicht dafür. Der Ladeplan nutzt nur das Haus (das Auto plant er selbst; vor 0.13
hat er es doppelt gezählt). Ältere Daten (Verlaufsimport, Monate vor dem Update) bleiben Summen, bis neue Viertelstunden sie ersetzen
(8 Werte je Platz).

**Akku-Reserve vor einer Spitze** (Schalter, **Standard aus**). Beim Batterie-Eintrag tragen Sie eine *Einstellung, die die Ladung hält*, und
ihren Wert ein (z. B. maximale Ausgangsleistung auf einen niedrigen Wert oder einen Modus wie Standby) sowie, wie viele Minuten vor einem
Risikofenster sie beginnt (Standard 60). Mit dem Schalter setzt der Wächter sie vor dem Fenster, damit der Akku nicht für den Eigenverbrauch
leer läuft und im Notfall noch helfen kann; nach dem Fenster stellt er den Wert zurück, den er vorgefunden hat. Er fasst nur Akkus mit
einer solchen Einstellung an, tut nichts, solange er den Akku für einen Notfall freigegeben hat, protokolliert jeden Schritt („Akku-Reserve:
… hält die Ladung …“) und protokolliert im Beobachtungsmodus nur. Nach einem Neustart oder beim Entladen der Integration wird ein gehaltener
Akku zuerst zurückgestellt. Wenn eigene Automationen dieselbe Einstellung ändern (z. B. beim Autoladen), entscheiden Sie, wer zuständig
ist – der Wächter stellt nur zurück, solange noch sein eigener Wert gesetzt ist.

**CSV-Export** (Dienst `viertelstunden_waechter.export_csv`). Schreibt das Viertelstunden-Lastprofil (120 Tage aufbewahrt: Beginn, Ende,
Bezug in kW und kWh, Schätzung ohne Wächter, Wallbox in kW) oder die Tagesspitzen (400 Tage) nach `config/viertelstunden_waechter/export/`
– kein öffentlicher Ordner. Format `standard` (Komma, Dezimalpunkt) oder `excel_de` (Semikolon, Dezimalkomma). Kleine Dateien kommen
zusätzlich in der Antwort des Dienstes zurück.

```yaml
action: viertelstunden_waechter.export_csv
data:
  kind: quarters      # oder days
  days: 31
  format: excel_de
```

**KI-Erklärer** (Schalter, **Standard aus und nach jedem Neustart aus**). In den allgemeinen Einstellungen eine *KI-Aufgabe* wählen
(Einstellungen > Geräte > KI-Aufgaben; Sie wählen das Modell, Cloud oder lokal – der Wächter hat keinen eigenen Schlüssel). Jeden Abend um
21 Uhr macht der Erklärer aus dem Protokoll des Tages 2 bis 4 einfache Sätze („Um 16:45 wurde die Wallbox von 16 auf 12 A gesenkt, weil …“),
zeigt sie im Sensor *Erklärung des Tages* und in der Ansicht Statistik und sendet sie über die Benachrichtigungsdienste. An einem Tag ohne
Eingriff wird keine KI gefragt (dann ein fester Satz). Höchstens 4 KI-Aufrufe am Tag; die KI schreibt nur Text – sie entscheidet und schaltet
nie. Dienst `viertelstunden_waechter.explain_today` (Feld `push`) fragt auf Wunsch.

## 3c. Ladeplan fürs Auto

Gerätetyp **Fahrzeug (Ladeplan)**. Er plant, in welchen Viertelstunden das Auto laden soll, damit es bis zur nächsten
Abfahrt sein Ziel erreicht, und zeigt den Plan an. **Das Ausführen ist ein eigener Schalter, standardmäßig aus.**

**Was Sie eintragen:** Ladestand des Autos (Sensor, %), Ziel (fester Prozentwert, optional aus einem Sensor wie dem
Ladelimit des Autos), Batteriekapazität (kWh), nächste Abfahrt (eine *Uhrzeit*-Entität – genommen wird das nächste
Auftreten – oder eine Datum-Uhrzeit-Entität / `input_datetime` / Zeitstempel-Sensor), höchste und niedrigste
Ladeleistung der Wallbox, Grundlast des Hauses und Ladewirkungsgrad, optional eine Entität „Auto angesteckt“ und optional die Befehle zum
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

**So richten Sie die Solarprognose ein:** Einstellungen > Dashboards > **Energie** > bei Ihrer Solaranlage (Solarmodule)
auf **Bearbeiten** > Schalter **„Solarproduktion vorhersagen“** einschalten > die Prognose-Integration wählen (z. B. die
Integration *Forecast.Solar*, die Sie vorher unter Einstellungen > Geräte & Dienste einrichten) > Speichern. Ohne diesen
Schritt kennt der Plan die Sonne nicht, auch wenn die Prognose-Integration installiert ist.

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
Entitäten **Ihrer** Installation (egal wie das Gerät heißt, auf Deutsch oder Englisch) in drei Ansichten: die Übersicht
(Einstellungen, Zusatzfunktionen, Geräte und Prioritäten, Jetzt, Kosten und Ersparnis), **Heute** – eine kompakte, einspaltige
Ansicht fürs Handy – und *Statistik und Prognose* (24-Stunden-Vorschau als Balken, Wochenprofil, Spitzen der letzten Tage,
Monate, Eingriffe je Tag, Ladeplan). Es werden nur Standardkarten benutzt. Ist in den allgemeinen Einstellungen ein Auto-Planer
gewählt, zeigt die Ladeplan-Karte dessen Plan statt des eigenen (siehe *Wächter und Auto-Planer zusammen*); nach dem Wählen oder
Entfernen eines Planers das Dashboard neu erstellen.

**So nutzen Sie ihn** (nur Administratoren): Entwicklerwerkzeuge → Aktionen → *Dashboard erstellen* ausführen und das YAML aus der
Antwort oder aus der angezeigten Benachrichtigung kopieren. Dann Einstellungen → Dashboards → Dashboard hinzufügen, öffnen, drei
Punkte → Bearbeiten → drei Punkte → Roher Konfigurationseditor, einfügen, speichern. Der Dienst **schreibt nie in ein bestehendes
Dashboard**, er liefert nur das YAML. Alle Dienste der Integration (`create_dashboard`, `import_history`, `send_week_report`,
`export_csv`, `explain_today`) dürfen nur Administratoren aufrufen (oder Automationen und Skripte).

**Die Ansicht *Heute* (fürs Handy)** zeigt von oben nach unten: den Status des Wächters; einen Balken mit der Prognose der laufenden
Viertelstunde gegen das Ziel (weißer Strich = Ziel, roter gestrichelter Strich = Grenze; grün = sicher darunter, gelb = knapp, rot =
über der Grenze); die Betriebsart (unterwegs zwischen *Aus*, *Nur beobachten* und *Aktiv* umschalten); Spitze heute, Spitze im Monat
und Eingriffe heute; ein Diagramm aller abgeschlossenen Viertelstunden von heute (rot = über der Grenze); die letzten Zeilen des
Protokolls von heute; und die Erklärung des Tages, wenn der KI-Erklärer an ist. Die Viertelstunden kommen aus dem Attribut
`today_quarters` des Sensors *Letzte Viertelstunde*. Am Handy das Dashboard öffnen und die Ansicht *Heute* wählen; es ist keine
zusätzliche Karte nötig.

Die Ansicht *Statistik und Prognose* braucht nichts Zusätzliches: Die Diagramme sind SVG-Bilder in normalen Markdown-Karten,
gezeichnet aus den Attributen der Sensoren; die Farben passen zu hellen und dunklen Designs.

| Diagramm | Was es zeigt | Quelle | Gefüllt nach |
|---|---|---|---|
| **Prognose** | Ein Balken je Stunde für die nächsten 24 h: voll = typischer Netzbezug, hell = höchster erwarteter Wert, rot = über dem Ziel, rot gestrichelt = Ziel | Lastprognose | Verlaufsimport (Minuten) oder einigen Tagen |
| **Typische Woche** | Wärmebild Wochentag × Stunde (0–23) in zwei Feldern: *Typisch* und *Höchste Werte*; Farbe von dunkelblau über türkis, grün und gelb bis orange = mehr Bezug (jedes Feld auf seinen eigenen Höchstwert skaliert), rot = über dem Ziel | Lastprognose | Verlaufsimport oder etwa 2 Wochen |
| **Höchste Viertelstunde je Tag** | Letzte 6 Wochen, ein Balken je Tag, rot über der Grenze, gestrichelt = Grenze | Attribut `peaks_by_day` des Sensors *Spitze heute* | ein Tag je Balken; frühere Tage per *Verlauf importieren* (Stundenmittel = Untergrenze) |
| **Spitze je Monat** | Ein Balken je Monat mit Wert, gestrichelter Umriss = Schätzung ohne Wächter, Linie = Grenze | Monatsverlauf des Sensors *Spitze im Monat* | ein Monat je Balken oder per *Verlauf importieren* |
| **Stundengraph** | Standard-Statistikgraph der Viertelstunden-Spitzen je Stunde, letzte 3 Tage | Langzeitstatistik | einigen Stunden |

Unter den Diagrammen stehen Tabellen für die höchsten Tage, die Monate und die Eingriffe je Tag. Bei zu wenig Daten steht statt der
Balken „noch zu wenig Daten“; das ist bei einer frischen Installation normal. Werden die Bilder nicht angezeigt, das Dashboard neu laden
(in der App den Frontend-Cache leeren).

---

## 3e. Rückmeldung, Vorwarnung und Wochenbericht

### Rückmeldung nach dem Befehl (immer an)

Ein „erledigt“ nach einem Dienstaufruf beweist nichts: Eine Cloud-Wallbox nimmt den Befehl an und ignoriert ihn, ein Stecker
ist offline. Der Wächter liest deshalb etwa **60 Sekunden nach jedem echten Eingriff** zurück, ob er angekommen ist:

| Gerät | Was zu sehen sein muss |
|---|---|
| Wallbox | der Strom-Wert steht höchstens beim neuen Wert, und nach der Phasenpause liegt die Ladeleistung nicht deutlich über dem, was der neue Strom erlaubt |
| Schaltbares Gerät | der Schalter ist aus |
| Drossel | die Zahl hat den neuen Wert |
| Batterie / Einstellung | der Freigabewert steht (es gibt nichts mehr freizugeben) |

Fehlt die Wirkung, wird der Befehl **einmal wiederholt**. Fehlt sie wieder, schreibt der Wächter es ins Protokoll, sendet eine
Meldung je Gerät (höchstens alle 30 Minuten) und lässt dieses Gerät **10 Minuten aus**: Der nächste Hebel der Reihenfolge kommt
dran, statt auf ein Gerät zu warten, das nicht reagiert. Reagiert es später wieder, wird es wieder benutzt. Das Zurückgeben wird
nicht geprüft: Klappt es nicht, bleibt das Gerät begrenzt und der Wächter versucht es erneut. Im Beobachtungsmodus wird nichts
geprüft (es wird ja nichts gesendet). Die Zahl steht im Attribut `unconfirmed` und im Wochenbericht; im Protokoll heißt es
„keine Reaktion … Befehl wird wiederholt“ und „Befehl nicht umgesetzt“.

### Vorwarnung (Schalter, Standard aus)

Schalter **Vorwarnung vor einem Eingriff**: Eine Meldung je Viertelstunde, wenn die Prognose der laufenden Viertelstunde 90 %
der Grenze erreicht und der Wächter noch nicht eingegriffen hat (ein Eingriff sendet eine eigene Meldung). Gut im Beobachtungsmodus,
um zu sehen, wie oft eine Viertelstunde knapp wird. Braucht Benachrichtigungsdienste in den allgemeinen Einstellungen.

### Wochenbericht (Schalter, Standard an)

Montags ab 07:00 sendet der Wächter einen kurzen Bericht über die letzte volle Woche (Montag bis Sonntag): höchste Viertelstunde
mit Tag und Uhrzeit, Tage über der Grenze, Eingriffe (echt, beobachtet, nicht umgesetzt), Spitze des Monats und – wenn Preise
eingetragen sind – Kosten und geschätzte Ersparnis. Ohne Messwerte der Woche (neue Installation) wird nichts gesendet.
Der letzte Bericht steht im Sensor **Wochenbericht** (Zustand = Woche, Attribut `text`) und am Ende der Ansicht Statistik.
Der Dienst **Wochenbericht senden** (`viertelstunden_waechter.send_week_report`, Felder `current_week`, `push`) erzeugt ihn auf
Wunsch, zum Beispiel zum Ansehen:

```yaml
action: viertelstunden_waechter.send_week_report
data:
  current_week: true   # die laufende Woche bisher statt der letzten vollen Woche
  push: false          # nur den Sensor füllen, keine Meldung senden
```

---

## 4. Allgemeine Einstellungen

| Einstellung | Wozu |
|---|---|
| **Nur nötig, solange** | Der Wächter greift nur ein, solange diese Entität an ist. Leer lassen = immer wachsam (empfohlen). |
| **„Aktiv“ sperren, solange** | Läuft noch ein alter Wächter oder eine Automation, die dieselben Geräte steuert: „Aktiv“ wird verweigert. |
| **Benachrichtigungsdienste** | z. B. `notify.mobile_app_handy` – Meldung, wenn die Grenze trotz aller Hebel nicht zu halten ist |
| **Betriebsart nach Neustart** | Wiederherstellen / Beobachten / Aktiv / Aus |
| **Netzspannung** | Spannung einer Phase, Standard 230 V (Europa); damit werden Ampere in Kilowatt umgerechnet |

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
- Jeder echte Eingriff wird nach etwa 60 s zurückgelesen: einmal wiederholt, dann gemeldet und das Gerät 10 min ausgelassen (siehe 3e).
- Entscheidungen nach Mittelwerten (Herd und Wasserkocher takten): Abschalten nach dem 1-Minuten-Mittel,
  Zurückgeben erst, wenn 2 Minuten lang genug Luft war.
- Der Wächter ersetzt **nicht** die Absicherung im Verteiler und kein vorgeschriebenes Lastmanagement.

---

## 7a. Geplant (noch nicht gebaut)

Erledigt in 0.13: Haus und Auto getrennt, Akku-Reserve, CSV-Export, KI-Erklärer, englische Texte, die Handy-Ansicht *Heute*. Die Reihenfolge ist ein Vorschlag, kein Versprechen.

1. **Veröffentlichung:** Der Installationstest auf einem frischen Home Assistant 2026.10.3 (Docker, `tests/install`) ist am 25.10.2026
   bestanden (Einrichtung von Grund auf, Geräte, Beobachten und Aktiv, Rückgabe, Dienste, Neustart) und **hassfest besteht**. Offen sind die
   HACS-Prüfung (braucht ein öffentliches Repository), Themen (Topics) im Repository, eine erste Version (Release) und Berichte von
   anderen Installationen.
2. **Tests mit echter Hardware** für *Leistung drosseln*, *Einstellungen ändern* (Wärmepumpen) und die Batterie-Freigabe anderer Hersteller;
   bis dahin nur im Simulator getestet. Testberichte sind willkommen (Vorlage *Gerätetestbericht*).
3. **Ladeplan näher an den Risikofenstern** und ein *Tagesplan* aus Solarprognose, Abfahrtszeiten und dem gelernten Lastmuster.
4. **Eine klügere Hausprognose:** Wetter, Außentemperatur und Solarprognose als zusätzliche Eingänge des gelernten Lastmodells
   (eine kältere Woche hebt die Heizlast, ein sonniger Tag senkt den Netzbezug). Das gelernte Muster aus Wochentag und Viertelstunde
   bleibt die Grundlage, das Wetter korrigiert es nur; ohne Wetter-Entität ändert sich nichts.
5. **Anbindungen (optional, nur auf Wunsch):** Den CSV-Export gibt es seit 0.13; wo eine Plattform eine dokumentierte Schnittstelle
   anbietet, könnte ein Connector die Daten dorthin senden (z. B. Plattformen für Energiegemeinschaften). Ein
   Connector hängt ganz von der Schnittstelle der anderen Plattform ab und ist ein eigener, optionaler Teil: Es verlässt nichts die
   Installation, solange der Nutzer es nicht einrichtet.
6. **Dynamische Tarife:** Laden nach Day-Ahead-Preis als weiterer Eingang des Plans (nur sinnvoll mit einem solchen Tarif).

### KI-Funktionen (Erklärer seit 0.13 gebaut, die anderen geplant)

Optional, **Standard aus und nach einem Neustart aus**, mit Tageskostengrenze. Die KI wird über die *KI-Aufgabe* (`ai_task`) von Home Assistant
benutzt: Jeder Nutzer wählt sein Modell (Cloud oder lokal), es ist kein Schlüssel eingebaut. **Die Regel: Die KI erklärt, berät und plant –
was jetzt geschaltet wird, entscheiden immer die festen Regeln** (alle 20 Sekunden, auch ohne Internet), und jeder KI-Vorschlag wird vor
der Verwendung gegen harte Grenzen geprüft.

| Funktion | Was sie macht | Risiko |
|---|---|---|
| **Erklärer** (gebaut, 0.13) | macht aus den Eingriffen des Tages einen kurzen Text, auf Wunsch als Meldung („Pool 12 min pausiert, damit das Auto bis 7 Uhr voll wird“) | keines, nur lesen |
| **Wochenrückblick mit Vorschlägen** | „Dreimal knapp, immer sonntags 18 Uhr mit Backrohr und Auto. Vorschlag: Ladestart auf 20 Uhr.“ Ohne Bestätigung ändert sich nichts | gering |
| **Einrichtung im Gespräch** | ein Satz wie „Pool ist mir egal, die Kühltruhe darf höchstens 30 min aus sein“ wird zum Vorschlag für Geräte, Prioritäten und höchste Auszeit, den der Nutzer bestätigt | gering |
| **Frage an den Wächter** | „Warum war gestern Abend die Wallbox gedrosselt?“ per Assist, Chat oder MCP-Server von Home Assistant | keines |
| **Tagesplan** | aus Solarprognose, Wetter, Terminen und gelerntem Lastmuster ein Vorschlag (z. B. Auto 11–15 Uhr laden, Akku-Reserve 30 %), vor der Verwendung von den Regeln geprüft | mittel, deshalb nur als Vorschlag |

Das Lernen der Lastmuster (Herd taktet, Backrohr am Sonntag) braucht schon heute kein Sprachmodell: Der Wächter macht es lokal mit einfacher
Statistik (siehe Lastprognose).

---

## 8. Häufige Fragen

**Nur das Auto?** Nein – überwacht wird der gesamte Netzbezug. Eingreifen kann er bei allen eingetragenen
Geräten.

**Was, wenn alle Hebel nicht reichen?** Gegen Ende der Viertelstunde eine Benachrichtigung (falls eingetragen).
Die Viertelstunde liegt dann über der Grenze.

**Zwei Regler an einer Wallbox** (z. B. zusätzlich evcc)? Steuert evcc die Wallbox, tragen Sie sie im Wächter als **evcc-Ladepunkt** ein,
nicht zusätzlich über ihre eigene Integration. Der Wächter setzt dann nur die Obergrenze in evcc, evcc regelt darunter.

**Braucht der Wächter Internet oder KI?** Nein. Alles läuft lokal.
