# Häufige Fragen (technisch)

Fragen, die Nutzer wirklich gestellt haben, mit kurzer Antwort. Mehr steht in der [Anleitung](ANLEITUNG.md).
*English: [FAQ.md](FAQ.md)*

## Einrichten

**Brauche ich eine PV-Anlage?**
Nein. Der Wächter braucht nur den Netzbezug. PV nutzt nur der Ladeplan, und dort ist sie optional.

**Welche Sensoren brauche ich?**
1. **Leistung Netzbezug** (Pflicht): in W oder kW, mit neuem Wert alle paar Sekunden. Ein Sensor, der beim Einspeisen negativ
   wird, geht auch.
2. **Zählerstand Netzbezug** (empfohlen): in Wh oder kWh, zählt nur den Bezug und steigt dauernd. Damit stimmt die
   Viertelstunde auch nach einem Neustart.

**Ich habe keinen eigenen Zähler, nur den Smart Meter des Netzbetreibers.**
Zwei Wege, siehe [Anleitung, Abschnitt 1](ANLEITUNG.md#ohne-pv-und-ohne-wechselrichter-zähler):
- Ein Messgerät im Verteiler, zum Beispiel ein Shelly mit Stromwandlern. Das ist der einfachste Start.
- Die Kundenschnittstelle des Smart Meters mit einem Lesekopf. Den Schlüssel dafür gibt der Netzbetreiber auf Anfrage heraus.

Das Webportal des Netzbetreibers reicht nicht: Die Werte kommen erst am nächsten Tag.

**Reichen Werte alle 15 Minuten oder stündlich?**
Nein, zum Regeln nicht. Der Wächter muss die *laufende* Viertelstunde sehen. Ein Wert, der älter als 2 Minuten ist, gilt als fehlend:
Der Wächter greift dann nicht ein und zeigt *keine Daten*. Spitzen und Kosten zeigt er trotzdem im Nachhinein.

**Mein Template-Sensor (z. B. aus einem Shelly 3EM Pro) fehlt in der Auswahl.**
Seit 0.13.3 lässt sich jeder Sensor wählen. Geprüft wird die **Einheit** (W/kW bzw. Wh/kWh), nicht die Geräteklasse.

**Wie richte ich einen Akku mit einstellbarem Mindest-Ladestand ein (ab 0.15)?**
Gilt für jeden Akku, bei dem sich in Home Assistant eine Untergrenze in Prozent einstellen lässt (Mindest-SOC, Entladegrenze,
Reserve). Beispiel mit einem Victron: Normal steht der Mindest-SOC auf 30 %, zum Abfangen einer Spitze soll der Akku bis 15 %
liefern. Beim Gerät *Batterie*:

| Feld | Eintrag |
|---|---|
| Ladestand | der SOC-Sensor des Akkus |
| Einstellung, die die Batterie freigibt / Wert | die Einstellung *ESS Minimum SOC* / `15` |
| Vorherige Werte wiederherstellen | an |
| Mindest-Ladestand folgt dem Ladestand zurück | an: Nach der Spitze geht das Minimum nicht auf einmal auf 30 %, sondern folgt dem Ladestand in den Schritten der Einstellung (beim Victron 5 %: 20, 25, 30), sonst lädt der Victron sofort aus dem Netz |
| Schrittweite Mindest-Ladestand | optional, z. B. `1`: dann 20, 21, 22 …, wenn Ihr Akku jedes ganze Prozent annimmt (einmal von Hand ausprobieren) |
| Nachladen ab | optional, z. B. 22:00: Hat die PV die 30 % bis dahin nicht geschafft, lädt der Akku aus dem Netz nach |
| Einstellung beim Nachladen / Wert | optional, z. B. *ESS maximaler Ladestrom* / `40`: damit langsam geladen wird, danach kommt der alte Wert zurück |
| Einstellung, die die Ladung hält / Wert | optional für die Akku-Reserve vor einer Spitze: *ESS Minimum SOC* / `soc` (bleibt beim aktuellen Ladestand) |

Eigene Automationen fürs Peak-Shaving (Min-SOC bei einer Spitze senken, danach zurückstellen, abends nachladen) braucht es
dann nicht mehr: **deaktivieren** (nicht löschen), sonst stellen zwei an denselben Werten. Die Betriebsart des Wächters muss *Aktiv*
sein, und beim Akku darf *Nur beobachten* nicht an sein. Beim ersten Mal im Protokoll nachsehen, ob alles wie erwartet läuft.

Mehr in der [Anleitung](ANLEITUNG.md), Abschnitt *Akku-Reserve vor einer Spitze*.

## Im Betrieb

**Betriebsart *Aktiv*, das Protokoll sagt „würde drosseln“, aber es passiert nichts.**
Jedes Gerät hat zusätzlich einen eigenen Schalter *Nur beobachten*. Ist er an, greift der Wächter bei diesem Gerät nie ein.
Seit 0.14.2 erscheint dann unter **Einstellungen > Reparaturen** ein Hinweis, und *Reparieren* schaltet es mit einem Klick aus.
Ohne Update: beim Gerät die drei Punkte > *Neu konfigurieren* > *Nur beobachten* aus.

**Ich habe die Grenze auf 4 kW gestellt, aber bei 7 kW greift der Wächter nicht ein.**
Prüfen Sie den Schalter **Bereits erreichte Spitze nutzen** (standardmäßig an). Ist die höchste Viertelstunde des Monats schon höher als Ihre
Grenze, gilt für den Rest des Monats diese Spitze statt der Grenze, weil Viertelstunden darunter nichts extra kosten. Bei einer erreichten
Spitze von 9,7 kW regelt der Wächter also gegen 9,7 kW, und 7 kW sind kein Anlass zum Eingreifen. Der Wert steht im Status-Sensor unter
`werte.limit_kw`, im Protokoll als „Grenze 9.7 kW“. Wollen Sie unabhängig von der Kostenfrage immer unter der eingestellten Grenze bleiben,
schalten Sie *Bereits erreichte Spitze nutzen* aus; in diesem Monat spart das dann kein Geld mehr, weil die Spitze schon bezahlt ist.
Weitere Punkte: Eine Wallbox wird nur bis zum Mindeststrom gesenkt und nie gestoppt (3-phasig bei 6 A etwa 4,1 kW, 1-phasig etwa 1,4 kW,
2-phasig etwa 2,8 kW). Zum Mithelfen braucht ein Speicher eine eingetragene Freigabe-Einstellung. Und bei *Nur beobachten* am Gerät wird nur
protokolliert (siehe die Frage davor).

**Die Viertelstunden-Prognose zeigt 10,96 kW, aber so viel hatte ich in den letzten 24 Stunden nicht.**
Der Wert ist keine Vorhersage aus der Vergangenheit. Er ist der Durchschnitt der *laufenden* Viertelstunde, wenn die Leistung so bleibt wie jetzt: (bisherige Energie + aktuelle Leistung x Restzeit) / 0,25 h. Eine kurze hohe Last, zum Beispiel Backofen, Wasserkocher oder ein Auto, das gerade zu laden beginnt, lässt ihn kurz springen, und er fällt zurück, sobald die Last endet. Abgerechnet wird nur der Durchschnitt der ganzen Viertelstunde, und den beobachtet der Wächter. Was das Haus üblicherweise braucht, zeigt *Typischer Bezug jetzt (Prognose)*, und die höchste erwartete Viertelstunde der nächsten 24 Stunden zeigen *Erwartete Spitze in 24 h (Prognose)* und die Grafik in der Ansicht *Statistik und Prognose*.

**Der Ladeplan startet und pausiert, stellt aber den Ladestrom nicht ein.**
Richtig, das tut er bisher nicht: Im geplanten Fenster lädt das Auto mit dem, was an der Wallbox eingestellt ist. Den Strom senkt
nur der Wächter, und nur, wenn eine Spitze droht. Der Ladeplan des Wächters ist ein einfacher Planer und bekommt keine neuen
Funktionen mehr. Wann und wie stark das Auto lädt, plant [Plugwhen](https://github.com/mobilewhatelse/plugwhen); dort ist das
Einstellen des Ladestroms geplant.

**Kann er meinen Wattpilot steuern?**
Ja, über die Integration `wattpilot-HA` (Ladestrom und Phasen). Das ist auf echter Hardware getestet.
Andere Wallboxen: siehe [Kompatibilität](KOMPATIBILITAET.md).

**Meine Wallbox hat den Ladestrom als Auswahlliste („6 A“, „8 A“ …), z. B. Anker SOLIX V1.**
Seit 0.14.3 nimmt das Feld *Einstellung Ladestrom* auch eine solche Liste. Der Wächter wählt den passenden Eintrag, nie einen
höheren, und drosselt stufenweise. Bis 0.14.2: als *Gerät mit Einstellung* eintragen, Wert `6 A` (genau wie in der Liste),
*Vorherige Werte wiederherstellen* an. Dann senkt er in einem Schritt auf 6 A.

Video (40 s, Testsystem, Wallbox nachgebildet; [als MP4](videos/wallbox_mit_auswahlliste.mp4)):

![Wallbox mit Auswahlliste hinzufügen](videos/wallbox_mit_auswahlliste.gif)

**Wie binde ich meinen Speicher ein, wenn ich schon eine eigene Min-SOC-Logik habe (z. B. Victron)?**
Ein erprobtes Beispiel von Markus (Victron, Spitzen unter 4 kW halten; der Min-SOC liegt normalerweise hoch, der Speicher wird nur für Spitzen
freigegeben, danach wird der Min-SOC auf den aktuellen Ladestand eingefroren; bei ihm: *Erwartete Entlastung* 2500 W, *Höchste Dauer* 15 Minuten,
vielen Dank für das Beispiel):
1. **Skript anlegen** (*Einstellungen > Automationen & Szenen > Skripte*, drei Punkte > *In YAML bearbeiten*). Die beiden Entitäten durch Ihre
   ersetzen (Min-SOC-Zahl und Ladestand-Sensor), das Präfix `number.` bzw. `sensor.` nur **einmal**:
   ```yaml
   alias: Min-SOC auf aktuellen Ladestand einfrieren
   sequence:
     - action: number.set_value
       target:
         entity_id: number.victron_settings_ess_batterylife_minimumsoc
       data:
         value: "{{ states('sensor.victron_system_battery_soc') | float(0) | round(0) }}"
   ```
   Einmal mit *Ausführen* testen: Die Min-SOC-Entität muss auf den aktuellen Ladestand springen. Der Wert muss im erlaubten Bereich der Entität liegen.
2. **Gerät *Batterie* im Wächter:** *Ladestand* = Ihr Ladestand-Sensor; *Mindest-Ladestand* z. B. 15 %; *Einstellung, die die Batterie freigibt* = die
   Min-SOC-Entität, *Wert für „freigegeben“* = der niedrige Min-SOC (z. B. `15`); *Vorherige Werte wiederherstellen* **aus**; *Skript nach dem
   Zurücknehmen* = das Skript aus Schritt 1. Ihre eigene Auslöse-Automation abschalten, sonst regeln zwei gleichzeitig.
3. **Zurücknehmen verstehen:** Der Wächter nimmt die Batterie erst zurück (und führt dann das Skript aus), wenn (a) die *Mindestdauer* vorbei ist
   (Standard 5 Minuten) **und** (b) der Spielraum größer ist als die *Erwartete Entlastung*. Der Spielraum kann höchstens **Grenze minus
   Sicherheitsabstand** betragen (4,0 − 0,3 = 3,7 kW). Steht die *Erwartete Entlastung* darüber (z. B. 4000 W), wird die Bedingung **nie** erfüllt,
   und die Batterie bleibt freigegeben, bis der Ladestand unter den Mindest-Ladestand fällt. Tragen Sie daher einen Wert **deutlich unter** der
   Grenze ein, der zu Ihrer üblichen Hauslast passt (z. B. 2500 W), und zusätzlich eine **Höchste Dauer** (z. B. 15 bis 30 Minuten) als Sicherheitsnetz.
4. **Voraussetzungen beim Victron:** Im ESS-Modus *Batterien geladen halten* wird der Min-SOC ignoriert, der Speicher hilft dann nicht. Damit der
   Wächter überhaupt eingreift, muss die wirksame Grenze erreicht sein (siehe die Frage zum Schalter *Bereits erreichte Spitze nutzen*).

**Kann er die Wärmepumpe auf „Bereitschaft“ stellen?**
Ja, Gerätetyp *Gerät mit Einstellung*: die Modus-Auswahl, Wert `Bereitschaft`. Zum Schutz *Komfort-Sensor* (z. B. Warmwasser),
*Mindestdauer* und *Pause nach dem Zurücknehmen* setzen, damit der Verdichter nicht taktet.

**Ich habe keine Wallbox, aber eine Heizpatrone (z. B. 3 Phasen mit je 1,5 kW). Geht das?**
Ja. Der Wächter braucht nur die Netzmessung, eine Wallbox ist nicht nötig.
- Phasen einzeln schaltbar (drei Schalter): drei *Schaltbare Geräte* mit eigener Priorität. Dann nimmt er nur so viel weg wie
  nötig (1,5, 3 oder 4,5 kW).
- Leistungssteller mit Zahlenwert (Prozent oder Watt): *Leistung drosseln*. Dann regelt er stufenweise.
- Nur als Ganzes schaltbar: ein *Schaltbares Gerät*, er schaltet dann alle 4,5 kW auf einmal.

Andere Großverbraucher mit einem Schalter in Home Assistant gehen genauso. Den Verbrauch eines einzelnen Geräts sieht er nur mit
einem eigenen Leistungssensor. Am Anfang ein paar Tage in der Betriebsart *Nur beobachten* laufen lassen: Er schaltet nichts und zeigt, was er
tun würde.

**Ich sehe kein Update.**
Updates kommen über den Marketplace (HACS) unter **Einstellungen > Updates**. Bis eine neue Version dort auftaucht, kann es ein paar
Stunden dauern.

**Warum komme ich trotz Wächter über die Grenze?**
Der Wächter kann nur senken, was er steuern darf, und nur so schnell, wie die Geräte und ihre Messwerte reagieren. Die häufigsten
Gründe: Es läuft mehr, als sich abschalten oder drosseln lässt (Herd, Backofen, Wärmepumpe ohne Eintrag). Ein Gerät steht auf
*Nur beobachten*. Eine Wallbox ist schon am Mindeststrom. Ein Befehl kommt spät an oder der Leistungswert des Geräts kommt über
eine Cloud nur alle paar Minuten. Oder der Abstand zur Grenze ist für die Anlage zu klein eingestellt. Im Protokoll *Letzte
Eingriffe* steht, was der Wächter versucht hat und was nicht umgesetzt wurde. Auch mit eingerichteter Wallbox kann es passieren, wenn
der Rest des Hauses allein schon nahe an der Grenze liegt: die Wallbox lässt sich nur bis zu ihrem Mindeststrom senken. Passiert es
regelmäßig und der Grund ist unklar, hilft die Taste *Rückmeldung senden* (mit Kontaktadresse, wenn Sie eine Antwort möchten).

**Welchen Leistungssensor trage ich bei der Wallbox ein?**
Möglichst einen, der direkt von der Wallbox kommt und die **gesamte** Ladeleistung zeigt, nicht nur eine Phase (L1) und nicht den
Wert aus der Cloud des Autos. Ein Sensor für nur eine Phase zeigt bei dreiphasigem Laden ein Drittel; ein Wert, der über eine
Cloud nur alle paar Minuten kommt, lässt den Wächter zu spät sehen, ob ein Befehl gewirkt hat.

**Eine Viertelstunde ist falsch verbucht (z. B. eine Spitze, die es nie gab). Wie korrigiere ich das?**
Mit der Aktion `viertelstunden_waechter.correct_quarter` unter **Entwicklerwerkzeuge > Aktionen** (nur Administratoren):
*Beginn* ist der Anfang der Viertelstunde in Ortszeit, z. B. `2026-11-16T06:15`. Mit einem *Wert* (kW laut Zähler) wird sie
ersetzt; **ohne Wert wird sie aus der Aufzeichnung genommen** (wenn der richtige Wert nicht bekannt ist). Die Spitze des Tages
und des Monats wird neu berechnet, im Protokoll steht eine Zeile, und der CSV-Export enthält danach den neuen Stand.
Ab 0.15 erkennt der Wächter den häufigsten Auslöser selbst: Stand der Bezugszähler länger als eine Viertelstunde still (Zähler
oder Verbindung weg) und bringt dann alles auf einmal, wird diese Viertelstunde nicht als Spitze verbucht.

## Dashboard

**Wie lege ich das Dashboard an?** (Administrator-Konto nötig)

Video (1 Min., Home Assistant 2026.11; [als MP4](videos/dashboard_anlegen.mp4)):

![Dashboard anlegen](videos/dashboard_anlegen.gif)

*Dashboard erzeugen lassen*
1. **Einstellungen > Werkzeuge** (in älteren Versionen links unten **Entwicklerwerkzeuge**), oben den Reiter **Aktionen**.
2. Im Feld *Aktion* „Dashboard erstellen“ tippen, **Viertelstunden-Wächter: Dashboard erstellen** wählen.
3. Unten rechts **Aktion ausführen**.
4. Darunter erscheint die Antwort, ein langer Text, der mit `views:` beginnt. Alles kopieren (Kopier-Symbol oder Strg+A, Strg+C).

*Leeres Dashboard anlegen*
1. **Einstellungen > Dashboards**, unten rechts **+ Dashboard hinzufügen**.
2. **Neues Dashboard von Grund auf**, Namen eingeben (z. B. „Spitzenwächter“), **Erstellen**.
3. Das neue Dashboard in der Seitenleiste öffnen.

*Text einfügen*
1. Oben rechts auf den **Stift** (Bearbeiten).
2. Oben rechts **drei Punkte > Raw-Konfigurationseditor**.
3. Alles markieren (Strg+A), löschen, den kopierten Text einfügen (Strg+V).
4. **Speichern**, mit dem **X** schließen, **Fertig**.

Danach hat das Dashboard drei Ansichten: *Übersicht*, *Heute* (fürs Handy) und *Statistik und Prognose*.

**Es klappt nicht.**
- **Fehler beim Speichern, Version 0.14.1 oder älter:** Dort enthält die Antwort das Dashboard zweimal. Auf 0.14.2 aktualisieren,
  oder den Text aus der Benachrichtigung (Glocke links unten) nehmen, ohne die Zeilen mit den drei Backticks.
- **„Entity … not found“:** Home Assistant nach dem Update einmal neu starten, dann die Aktion noch einmal ausführen.
- **Aktion nicht in der Liste:** Der Wächter ist noch nicht eingerichtet, oder Home Assistant wurde nach der Installation nicht
  neu gestartet.
- **Kein „Raw-Konfigurationseditor“ im Menü:** Erst auf den Stift klicken. Das Menü gibt es nur im Bearbeiten-Modus.

## evcc

**evcc kann den Netzbezug auch auf z. B. 10 kW begrenzen. Was ist der Unterschied?**
evcc begrenzt die Leistung **im Moment**, und nur an seinen Ladepunkten. Abgerechnet wird aber der **Mittelwert der Viertelstunde**.
Der Wächter rechnet mit diesem Mittelwert: Kurze Spitzen (Wasserkocher, Backrohr) gleicht er aus, ohne gleich das Auto zu bremsen.
Er kann außerdem jedes Gerät in Home Assistant einbeziehen, nicht nur die Wallbox.
Wer nur evcc und eine Wallbox hat und eine feste Grenze will, kommt mit evcc aus. Beides geht auch zusammen: Der Wächter setzt dann nur
die Obergrenze in evcc.

**Im Protokoll steht oft „Netzbezug: Ihr Sensor zeigt 8,6 kW, evcc zeigt 4,1 kW“, kurz darauf umgekehrt. Ist etwas falsch?**
Nein. Der Wächter regelt immer mit dem Sensor, den Sie bei ihm als Netzbezug gewählt haben. Springen die Werte so hin und her, liest
evcc den Netzbezug aus einer anderen, verzögerten Quelle (Beispiel aus einer Rückmeldung: evcc vom Anker über die Cloud, der Wächter
direkt vom Smartmeter des Netzbetreibers). Bei Lastsprüngen zeigt dann eine Quelle schon den neuen Wert, die andere noch den alten.
Abhilfe: in evcc denselben Zähler als Netzzähler einstellen wie im Wächter; dann zeigen beide dasselbe.

## Allgemein

**Kann ich den Wächter für einen zweiten Zählpunkt (zweites Haus) doppelt laufen lassen?**
Noch nicht. Der Wächter erlaubt einen Eintrag je Home Assistant, und seine Dienste sprechen immer diesen einen an. Für einen zweiten Zählpunkt: entweder weglassen, oder, wenn beide gemeinsam abgerechnet werden (eine Spitze für beide), die beiden Leistungen in einem Template-Sensor addieren und diesen als Netzleistung eintragen. Mehrere Zählpunkte sind für eine spätere Version geplant (etwa Februar 2027, keine Zusage).

**Braucht der Wächter Internet oder KI?**
Nein. Alles läuft lokal.
