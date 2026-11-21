# Kompatibilität: Wallboxen, Batterien, Wärmepumpen

Der Wächter kennt keine Marken, nur Rollen (siehe README). Ob **Ihr** Gerät funktioniert, hängt davon ab, welche
Entitäten die Home-Assistant-Integration des Geräts anbietet. Diese Seite zeigt, was geprüft wurde und wobei wir
die Hilfe der Community brauchen. *Stand der Prüfung: 25.10.2026, Integrationsversion 0.12.0 (der Wattpilot-Test lief mit 0.11.0).*

## Bedeutung der Symbole

| Symbol | Bedeutung |
|---|---|
| ✅ | **Getestet.** Mindestens ein Abend im Modus *Aktiv* mit einem echten Eingriff und beobachtetem echtem Zurücknehmen, auf echter Hardware, gemeldet mit Versionsnummer (siehe unten). |
| ⚠️ | **In Prüfung.** Auf echter Hardware im Modus *Aktiv* eingegriffen und zurückgenommen, aber die Wirkung auf die Leistung ist noch nicht eindeutig belegt (z. B. weil eine Cloud die Leistung nur selten meldet). |
| 🟡 | **Bei den Autoren im Einsatz.** Ihre Hardware, Beobachtungsmodus mit dieser Integration (der Freigabe-Weg wurde im echten Betrieb noch nicht ausgelöst), oder dieselben Entitäten werden von den eigenen Automationen bzw. dem Vorgänger-Skript benutzt. |
| 🔍 | **Entitätstypen im Quelltext der Integration bestätigt** (Version aus Home Assistant 2026.10). Auf Hardware **nicht** getestet; ob Ihr Modell oder Ihre Firmware die Funktion unterstützt, ist offen. |
| ❔ | **Nicht geprüft / Hilfe gesucht.** Die Integration hat die Plattformen (`number`, `select`, `switch`), die Entitäten entstehen aber aus Gerätedefinitionen oder wurden nicht angesehen. Bitte testen und melden. |
| ❌ | **Keine passende Entität gefunden** (nichts Schreibbares, das die Leistung senkt oder den Modus ändert). Skript oder Ein/Aus-Schalter verwenden. |

**„Getestet“ heißt:** mindestens ein Abend im Modus **Aktiv** mit einem echten Eingriff **und** beobachtetem
echtem Zurücknehmen, auf echter Hardware, gemeldet mit Versionsnummer. Bisher haben der Wattpilot (durch die Autoren, 25.10.2026), die Anker SOLIX V1 und die Anker Solarbank 3 Pro
(beide durch einen Nutzer, 15.11.2026) diese Stufe erreicht; die anderen Gerätetypen – Leistung drosseln, Einstellung ändern – noch nicht.
Melden Sie Ihr Gerät – siehe „So melden Sie einen Test“.

## Bei anderen im Einsatz (aus der freiwilligen Statistik)

Wer *Anonyme Daten teilen* eingeschaltet hat, sendet, aus welchen Integrationen seine Netzsensoren und Geräte kommen
(nur der Name der Integration, sonst nichts). Stand 21.11.2026, aus 73 Installationen (63 in Österreich, 8 in Deutschland, je 1 in der Schweiz und Slowenien; 64 davon beobachtend, 9 eingreifend), sind diese mit dem Wächter im
Einsatz. **Im Einsatz heißt nicht getestet:** Wir wissen nicht, ob der Wächter dort eingegriffen hat, nur dass er eingerichtet ist.

- **Wechselrichter und Zähler:** Fronius, Huawei Solar, Shelly (auch Shelly Cloud DIY), SolarEdge Modbus (auch Multi), Kostal Plenticore, GoodWe, Victron GX, HomeWizard, Tibber, FoxESS Modbus, SolaX Modbus, SunSpec, Solar Manager, EcoTracker, Powerfox, EDL21 (Smart-Meter-Leser)
- **Wallboxen:** Fronius Wattpilot, go-e Charger (`goecharger_api2` und `goecharger_mqtt`), Charge Amps, NRGkick, openWB (MQTT), Tuya EV Charger und jede Wallbox über **evcc** (der häufigste Weg, auch mit der evcc-Integration `evcc_intg`)
- **Hausakkus:** sonnenBatterie, Anker Solix (auch die offizielle Integration), Jackery
- **Autos:** FordPass, Mercedes (`mbapi2020`), MySkoda und Škoda, VW-Gruppe (`vag_connect`), BYD, Tesla Fleet
- **Sonstige:** Tuya Local, Sonoff, Matter

Allgemeine Bausteine (Template, MQTT, Verbrauchszähler, Integral, Min/Max, Gruppe) sind weggelassen. Sie nutzen den Wächter
mit einem dieser Geräte? Ein kurzer Bericht in den Issues hilft allen, siehe „So melden Sie einen Test“ unten.

## Wallboxen (Gerätetyp *Wallbox*)

Braucht einen Leistungssensor und einen einstellbaren Ladestrom (`number`, A).

| Integration | Ladestrom | Status |
|---|---|---|
| Wattpilot (Community, `wattpilot-HA`) | `number` „Max Charging Current“, Phasenwahl | ✅ Autoren, 25.10.2026, 0.11.0: Auto lädt mit 11 kW, Herd und Backrohr dazu; in Stufen 16 → 12 → 10 → 8 → 6 A gesenkt, schrittweise wieder angehoben, „wieder 16 A“ protokolliert; Laden nie gestoppt, Viertelstunde unter dem Ziel. Noch nicht gesehen: Umschalten auf 1 Phase |
| Anker SOLIX V1 Smart EV Charger (Community, Anker Solix) | Ladestrom als Auswahlliste („6 A“, „8 A“ …), seit 0.14.3 | ✅ Nutzer, 15.11.2026, 0.14.4: Auto lädt, Backrohr, Warmwasser und Wärmepumpe dazu; auf 8 A gedrosselt, bei mehr Luft auf 9 A zurück, „wieder frei (9 A)“ protokolliert, also genau auf den Wert vor dem Eingriff; der Ladestrom ändert sich in der App. Am 20.11.2026 noch einmal bestätigt (Nutzer: „funktioniert“, Version nicht genannt): von 12 A auf 10 A (3-phasig, 0,7 kW zu viel) und nach vier Minuten wieder auf 12 A („wieder frei“). **Hinweis:** Die Leistung kommt über die Anker-Cloud, die ohne MQTT nur alle 60 bis 300 Sekunden aktualisiert. Ab 0.15 misst der Wächter diesen Abstand und wartet entsprechend, bevor er „nicht umgesetzt“ meldet |
| Wallbox (Home Assistant) | `number` „Maximum charging current“ | 🔍 |
| OpenEVSE (Home Assistant) | `number` „Charge rate“ (A) | 🔍 |
| Zaptec (Community) | `number` „charger_max_current“ | 🔍 |
| OCPP (Community, `lbbrhzn/ocpp`) | `number` „Maximum Current“ (Ladeprofil) | 🔍 |
| Alfen (Community) | mehrere „max current“-Zahlen (Geräteeinstellungen, häufiges Schreiben nicht geprüft) | 🔍 mit Vorsicht |
| Tesla Fleet (Home Assistant), Ladestrom des Autos | `number` „charge current request“ (das Auto, keine Wallbox) | 🔍 |
| KEBA (Home Assistant), Easee (Community) | nur ein Dienst, keine Zahl | 🔍 über Hilfsgröße (`input_number` + Automation) |
| Ohme, Blue Current (Home Assistant), myenergi | keine Strom-Zahl | ❌ |
| evcc (jede Wallbox, die evcc steuert) | eigener Gerätetyp *evcc-Ladepunkt*: der Wächter setzt den maximalen Ladestrom des Ladepunkts über die REST-Schnittstelle von evcc (keine Integration nötig). Getestet am 09.11.2026 gegen einen Demo-evcc 0.319.0 mit simulierter Wallbox, nicht an Hardware | 🔍 experimentell |
| go-e Charger (Community, `marq24/ha-goecharger-api2`; Gemini, Gemini flex, HOMEfix) | `number` in A (6-32 A, Schritt 1); Phasenmodus als `select` `psm`. Im Quellcode geprüft am 05.11.2026. Am 19.11.2026 von einem Nutzer bestätigt (Rückmeldung aus der freiwilligen Statistik, Version 0.14.4, Betriebsart *Aktiv*, `goecharger_api2`): „positiver Praxistest“. **Hinweis des Nutzers:** Die Anzahl der Phasen muss mit einem eigenen Helfer aus den Phasenströmen ermittelt werden | ✅ |
| openWB, Tesla Wall Connector, andere | | ❔ |

## Hausbatterien und Wechselrichter (Gerätetyp *Batterie* oder *Einstellung ändern*)

Der Wächter gibt die Batterie im Notfall frei: Er setzt ein oder zwei Einstellungen auf einen Wert, bei dem die
Batterie das Haus versorgt (maximale Ausgangs-/Entladeleistung, Betriebsmodus), und stellt sie wieder zurück.
Braucht einen Ladestand-Sensor.

| Integration | Schreibbare Entitäten (gefunden) | Idee für „freigegeben“ | Status |
|---|---|---|---|
| Jackery (Installation der Autoren) | `select` Auto-Standby-Modus, `number` maximale Ausgangsleistung (Netz), `sensor` Ladestand | Modus `on`, Leistung `800` | 🟡 |
| Anker Solarbank 3 Pro (Community, Anker Solix) | Einstellungen der Solarbank | Ausgabe ins Haus freigeben | ✅ Nutzer, 15.11.2026, 0.14.4: „Batterie freigegeben (1.4 kW zu viel, Ladestand 30 %)“, nach 14 Minuten „wieder wie vorher“ protokolliert; das Abgabelimit wurde dabei von 100 auf 350 W gestellt und wieder zurück (vom Nutzer in der App gesehen, bestätigt 17.11.2026). Am 20.11.2026 noch einmal (Nutzer: „funktioniert“): drei Freigaben innerhalb einer Stunde, jeweils nach zwei bis drei Minuten zurückgegeben, die Ausgabe ging von 100 auf 350 W. Als Balkonkraftwerk-Speicher gibt sie höchstens 800 W ab, die Wirkung gegen eine Spitze ist also klein |
| Fronius (Home Assistant) | `number` Entladeleistungs-Limit (+ Aktivierungs-Schalter), Ladeleistungs-Limit, Mindest-Reserve, AC-Leistungs-Limit; `switch` Laden aus dem Netz | Entladelimit anheben oder Mindest-Reserve senken | 🔍 |
| Kostal Plenticore (Home Assistant) | `number` Batterie-Mindest-SOC, Mindest-Hausverbrauch, Wirkleistungsbegrenzung; `select` Batterie-Laden | Mindest-SOC senken / Mindest-Hausverbrauch setzen | 🔍 |
| GoodWe (Home Assistant) | `number` Entladetiefe, Ladestrom, Einspeisebegrenzung; `select` Betriebsmodus | Betriebsmodus / Entladetiefe | 🔍 Angaben eines Testers (GW10KN-ET mit Smart Meter, BYD HVS), mit dem Wächter noch nicht getestet: Betriebsmodus mit den Optionen Allgemein, Netzunabhängig, Backup, Eco, Spitzenlastreduzierung. **Achtung:** „Active Power“ ist bei Netzbezug **negativ**; als Netzbezug eine Vorlage mit umgedrehtem Vorzeichen oder evcc eintragen. |
| Growatt (Home Assistant, Cloud) | `number` Entladeleistung(s-Limit), Ladegrenzen; `switch` AC-Laden | Entladeleistung anheben (Cloud-Verzögerung) | 🔍 |
| Enphase Envoy (Home Assistant) | `select` Speichermodus; `number` Reserve-SOC; `switch` Laden aus dem Netz | Speichermodus / Reserve senken | 🔍 |
| Powerwall über Tesla Fleet (Home Assistant) | `number` Backup-Reserve in Prozent | Backup-Reserve senken (Cloud-Verzögerung) | 🔍 |
| SolarEdge Modbus (Home Assistant) | `number` Entladelimit, Ladelimit, Backup-Reserve; `select` Speicher-Steuer-/Standard-/Befehlsmodus | Befehlsmodus / Entladelimit | 🔍 |
| HomeWizard Batterie (Home Assistant) | `select` Batterie-Gruppenmodus | der Modus, der entlädt | 🔍 |
| Imeon (Home Assistant) | `select` Manager-Wechselrichtermodus | der entladende Modus | 🔍 |
| Sigenergy lokal per Modbus (Community) | `number` ESS maximale Entladegrenze; `select` Remote-EMS-Steuermodus | Entladegrenze anheben | 🔍 |
| Huawei SUN2000, SolaX Modbus, EcoFlow, Zendure, Victron Modbus, AlphaESS, Anker Solix (andere Modelle), SolarEdge Modbus Multi (Community) | Plattformen vorhanden, Entitäten aus Gerätedefinitionen erzeugt | | ❔ |
| SMA, SolarEdge (Cloud), Powerwall, Victron GX, Solarman, Solax, Bluetti Modbus, KACO Modbus (Home Assistant) | nichts Schreibbares gefunden, das die Leistung senkt | | ❌ |

Cloud-Integrationen (Growatt, Tesla, EcoFlow …) reagieren mit Sekunden bis Minuten Verzögerung. Ein Wächter, der
mit 15-Minuten-Mittelwerten arbeitet, kommt damit zurecht – aber bitte testen.

## Wärmepumpen (Gerätetypen *Leistung drosseln*, *Einstellung ändern*, *Schaltbares Gerät*)

Es gibt drei Arten der Steuerung (siehe README): eine **Leistungsbegrenzung** als Zahl, einen **Sperrkontakt /
SG-Ready** als Schalter, einen **Betriebsmodus** als Auswahl.

| Integration | Schreibbare Entitäten (gefunden) | Verwendung | Status |
|---|---|---|---|
| NIBE Modbus (Home Assistant) | number / select / switch aus den schreibbaren Registern des Pumpenmodells erzeugt | modellabhängig: Leistungsbegrenzung, Modus, Sperre | ❔ vielversprechend |
| Viessmann ViCare (Home Assistant) | `select` Warmwasser-Betriebsmodus; `number` Heizkurven-Verschiebung und -Neigung, Warmwasser- und Raumtemperaturen; `switch` Schnellmodus | keine Leistungsbegrenzung: Modus oder Temperatur-Verschiebung (Komfort-Abwägung) | 🔍 |
| MELCloud (Home Assistant) | `select` Betriebsmodus; `number` Vorlauftemperatur | Betriebsmodus | 🔍 |
| MELCloud Home (Home Assistant) | `switch` Standby, Frost-/Überhitzungsschutz; `number` Schutztemperaturen | Standby-Schalter | 🔍 |
| LG ThinQ (Home Assistant) | `select` Betriebsmodus; `switch` Betriebsleistung | vor allem Haushaltsgeräte / Klimageräte | 🔍 |
| Midea (Home Assistant) | `switch` Strom, Zusatzheizung …; `select` Modus | vor allem Klimageräte | 🔍 |
| Daikin (Home Assistant) | `switch` Zone / Umschalter; Klima | nur Ein/Aus | ❌ für Leistung, 🔍 für Ein/Aus |
| Modbus (Home Assistant, allgemein) | jedes Register, das Sie als `number` / `switch` / `select` anlegen | wenn Ihre Wärmepumpe ein Register für Leistungsgrenze, Modus oder Sperre dokumentiert | 🔍 Prinzip |
| SG-Ready über zwei Relais (z. B. Shelly) | zwei `switch`-Entitäten | *Einstellung ändern*: Schalter 1 `on`, Schalter 2 `off` = Modus 1 (Sperre) | 🔍 Prinzip |
| Ariston, Stiebel Eltron, Weheat, Wolf SmartSet, BSB-LAN, ATAG, Mitsubishi Comfort, Hisense, Fujitsu (Home Assistant); Luxtronik, myVaillant, Daikin Altherma, NIBE (Community) | nicht im Detail geprüft | | ❔ |

Wärmepumpen brauchen besondere Sorgfalt: Nutzen Sie **Komfort-Sensor**, **Mindestdauer**, **Pause nach dem
Zurücknehmen** und **Höchste Dauer**, und starten Sie im Beobachtungsmodus.

## So melden Sie einen Test

Eröffnen Sie ein Issue mit dem Titel „Gerätetest: <Integration> <Modell>“ und schreiben Sie:

1. Integration (Home Assistant oder Community-Integration aus dem Marketplace, Version) und Gerätemodell / Firmware
2. Verwendeter Gerätetyp (Wallbox / schaltbares Gerät / Batterie / Einstellung ändern / Leistung drosseln) und die Entitäten
3. Betriebsart (Beobachten oder Aktiv), Zahl der Abende, was der Wächter getan hat (die `today`-Zeilen des
   Status-Sensors, der Diagnose-Download ohne private Daten)
4. Hat das Zurücknehmen funktioniert? Etwas Auffälliges (Verzögerungen, zurückspringende Werte, Fehlermeldungen)?

Berichte, die die Stufe „getestet“ erreichen, werden mit der Integrationsversion in die Tabelle übernommen.
