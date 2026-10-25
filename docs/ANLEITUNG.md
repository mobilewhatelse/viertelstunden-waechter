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

### Notfall-Aktion (Skript)

Für alles, was sich nicht einfach schalten lässt, vor allem den **Hausakku**: Jeder Akku wird anders gesteuert
(Lademodus, Entladeleistung, Standby …), deshalb zwei kleine Skripte – eines greift ein, eines nimmt es zurück.

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
