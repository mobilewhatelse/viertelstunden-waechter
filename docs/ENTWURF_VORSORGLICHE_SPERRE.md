# Entwurf: Vorsorgliche Sperre vor dem Anlauf (Issue #5)

Stand: Entwurf zum Testen für die Version um den 13.12.2026, **Standard aus**. Zweig `sperre-entwurf`.

## Worum es geht

Eine Wärmepumpe mit EVU-Sperrkontakt (als Gerät vom Typ *Einstellung ändern* eingetragen, Sperrkontakt → `on`) zieht beim
Anlauf sofort 4 bis 5 kW. Liegt das Haus schon bei 5 bis 6 kW, ist die Viertelstunde praktisch sofort über der Grenze. Bisher
griff der Wächter erst ein, wenn die Wärmepumpe schon lief, und sperrte sie direkt nach dem Start wieder: ein kurzer Takt für
den Verdichter. Die vorsorgliche Sperre verhindert den Anlauf, solange er nicht passt, statt ihn danach abzuwürgen.

## Funktionsweise

Alle 20 Sekunden, für jedes Gerät vom Typ *Einstellung ändern* mit einer Anlaufleistung größer 0:

- **Spielraum** = `min(erlaubt, Ziel) − Netzbezug` (Netzbezug als Mittel der letzten 60 Sekunden, wie bei der normalen
  Regelung). *Erlaubt* ist der Durchschnitt, der bis zum Ende der Viertelstunde noch passt, *Ziel* = Grenze − Sicherheitsabstand.
- **Sperren**, wenn das Gerät **nicht läuft** (Leistung unter *Läuft ab*, oder die *Läuft-Entität* ist aus) und der Spielraum
  **kleiner als die Anlaufleistung** ist. Gesperrt wird mit genau denselben Werten wie beim normalen Eingriff (Einstellung und
  *Wert für „gesenkt“* des Geräts, z. B. Sperrkontakt `on`).
- **Freigeben**, sobald der Spielraum mindestens Anlaufleistung + 0,2 kW beträgt. Zurückgestellt wird wie bei der normalen
  Rücknahme „wieder wie vorher“: nur die Einstellungen, die noch den Sperrwert haben (eine inzwischen echte EVU-Sperre bleibt).
- Die vorsorgliche Sperre ist **kein Eingriff** im Sinne der Statistik: keine Push-Meldung, kein Zähler „Eingriffe heute“, der
  Status bleibt *bereit*. Sie steht in *Letzte Eingriffe* bzw. im Protokoll:
  - `Vorsorgliche Sperre: Wärmepumpe gesperrt (Spielraum 2.1 kW, Anlauf 5.0 kW)`
  - `Vorsorgliche Sperre: Wärmepumpe freigegeben (Spielraum 5.4 kW)`
- Getrennt von der normalen Regelung gespeichert (`Guard.precaution`), damit deren Reihenfolge beim Zurückgeben unverändert
  bleibt. Ohne Gerät mit Anlaufleistung läuft der Code gar nicht (Test „aus = wie bisher“).

## Einstellung (Gerät *Einstellung ändern*)

| Feld | Standard | Bedeutung |
|---|---|---|
| Anlaufleistung | 0 (aus) | kW direkt nach dem Start, z. B. 5 |
| Leistungssensor | leer | Leistung der Wärmepumpe; daran sieht der Wächter, ob sie läuft, und das Anlauf-Protokoll misst die Spitzen |
| Läuft ab | 100 W | ab dieser Leistung gilt das Gerät als laufend |
| Läuft-Entität | leer | optional, hat Vorrang vor dem Leistungssensor (an = läuft) |
| Höchstdauer | 30 min | länger dauert eine vorsorgliche Sperre nie |
| Mindestabstand | 3 min | zwischen zwei Änderungen am Gerät (Sperre, Freigabe) |

Ohne Leistungssensor und ohne Läuft-Entität lässt sich die Anlaufleistung nicht speichern (der Wächter muss wissen, ob das Gerät
läuft). Ebenso nicht, wenn *Vorherige Werte wiederherstellen* aus ist und kein Skript gewählt ist (sonst bliebe die Sperre).

**Vorschlag für die Anlaufleistung:** Der Status-Sensor zeigt im Attribut `precaution` (und auf der Karte *Vorsorgliche Sperre
(Entwurf)* der Hauptseite, nach *Dashboard neu erstellen*) z. B. „Gemessene Anlaufspitze: 4.6 kW (Median aus 7 Läufen)“: Median
der höchsten Leistung in den ersten drei Minuten jedes Laufs der letzten 30 Tage, ab 3 Läufen (Läufe mit einem Sensor, der nur
alle 30 s oder seltener meldet, zählen nicht: er sieht die Spitze nicht). Er wird **nie** automatisch
übernommen. Dafür braucht es den Leistungssensor schon einige Tage vorher (Anlaufleistung darf dabei 0 bleiben).

## Sicherheitsnetze

- **Nie ein Gerät, das läuft.** Das bleibt Sache der normalen Regelung. Läuft es trotz Sperre an, wird die vorsorgliche Sperre
  zurückgenommen, die normale Regelung übernimmt.
- **Höchstdauer** (Standard 30 min): danach Freigabe mit Hinweis und für dieselbe Zeit keine neue vorsorgliche Sperre. Die
  Wärmepumpe bleibt also höchstens etwa die Hälfte der Zeit vorsorglich gesperrt, nie dauerhaft.
- **Mindestabstand** (Standard 3 min) zwischen Sperre und Freigabe, auch zu einer Änderung der normalen Regelung.
- **Bestehende Sperren bleiben unberührt:** Hat der Sperrkontakt schon den Sperrwert (echte EVU-Sperre, Nutzer), sperrt der
  Wächter nicht zusätzlich und gibt auch nichts frei.
- **Komfort-Minimum:** Liegt der Komfort-Sensor (Raum, Warmwasser) unter dem Minimum, wird nie vorsorglich gesperrt, eine
  bestehende Sperre wird aufgehoben. Ebenso, wenn die Entität *Eingriff nur, solange* aus ist.
- **Sperre nicht übernommen:** Zeigt die Einstellung nach 90 s nicht den Sperrwert, gibt der Wächter auf und lässt das Gerät
  10 min aus.
- **Zurückgeben** bei Neustart (Merker im Speicher wie bei der normalen Regelung), Wechsel der Betriebsart, fehlenden
  Messwerten (90 s), *nicht nötig* (Bedingung aus) und beim Beenden der Integration.
- **Nichts Neues wird gesendet:** Leistungssensor und Läuft-Entität eines Geräts *Einstellung ändern* gehen weder in den
  Geräte-Check noch in die Einrichtungsübersicht der Statistik.

## Grenzen und Risiken

- **Verdichter-Takt:** Die Sperre selbst schaltet keinen laufenden Verdichter. Aber Freigabe und erneute Sperre vor dem Anlauf
  können die Steuerung der Wärmepumpe verwirren; viele Wärmepumpen haben nach einer EVU-Sperre eine eigene Wiederanlaufsperre
  oder Mindest-Stillstandszeit (oft 5 bis 20 min). Dann läuft die Wärmepumpe nach der Freigabe nicht sofort an, und der Spielraum
  kann bis dahin schon wieder weg sein.
- **EVU-Zeiten des Netzbetreibers:** Netzbetreiber erlauben die EVU-Sperre oft nur bis zu 3 × 2 Stunden am Tag. Der Wächter zählt
  diese Zeiten nicht, die Höchstdauer begrenzt nur eine einzelne Sperre. Wer einen echten EVU-Kontakt mitbenutzt, sollte das mit
  dem Netzbetreiber und dem Hersteller klären. Im gemeldeten Fall simuliert ein Tasmota-Relais den Kontakt.
- **Wärmepumpen mit eigener Anlaufbegrenzung** (Inverter, Sanftanlauf): Die Anlaufspitze ist kleiner und dauert kürzer; eine zu
  hoch eingetragene Anlaufleistung sperrt unnötig oft. Den gemessenen Vorschlag nehmen.
- **Komfort:** In Zeiten mit dauerhaft hohem Hausverbrauch (Kochen, Wallbox) startet die Wärmepumpe später. Die Höchstdauer
  begrenzt das, ersetzt aber kein Komfort-Minimum (Komfort-Sensor eintragen).
- **Absturz zwischen Sperre und Speichern:** Der Merker wird wie bei der normalen Regelung nach etwa 10 s gespeichert. Stürzt Home
  Assistant genau dazwischen ab, bleibt das Relais im Sperrwert, bis man es von Hand zurückstellt (gleiches Risiko wie bisher).
- **Leistungssensor selten:** Meldet er nur alle paar Minuten, merkt der Wächter einen Anlauf spät; die Läuft-Entität ist dann
  besser.
- Nur der Typ *Einstellung ändern*. Erweiterungspunkte im Code: `engine.PC_KINDS`, `Guard._pc_lock` (Befehl je Typ) und der Block
  im Config-Flow (`_device_schema`, Typ *Einstellung ändern*).

## So testen

1. Leistungssensor der Wärmepumpe beim Gerät eintragen, Anlaufleistung 0 lassen, einige Tage laufen lassen. Status-Sensor,
   Attribut `precaution`, zeigt dann die gemessene Anlaufspitze.
2. Anlaufleistung eintragen (Vorschlag oder Datenblatt) und zuerst beobachten: entweder Betriebsart *Beobachten* oder beim Gerät
   *Nur beobachten*. Im Protokoll stehen dann Zeilen wie „hätte vorsorglich gesperrt (Spielraum 2.1 kW, Anlauf 5.0 kW)“ und, wenn
   die Wärmepumpe tatsächlich anläuft, „eine Sperre hätte diesen Anlauf verschoben“.
3. Wenn die Zeilen plausibel sind: scharf schalten (Betriebsart *Aktiv*, *Nur beobachten* aus). Log lesen: *Letzte Eingriffe*
   auf dem Dashboard, oder Einstellungen > System > Protokolle (Logger `custom_components.viertelstunden_waechter`).
4. Achten auf: Wie oft und wie lange gesperrt? Startet die Wärmepumpe nach der Freigabe? Kommt „Höchstdauer“ häufig vor (dann
   Anlaufleistung zu hoch oder Grenze zu knapp)? Gab es trotzdem Viertelstunden über der Grenze?

Automatische Tests: `tests/test_vorsorge.py` (Haus 5,5 kW + Anlauf 5 kW → gesperrt, Haus 2 kW → frei, Höchstdauer,
Mindestabstand, läuft schon, Beobachten, Nur beobachten, Neustart, fehlende Messwerte, EVU-Sperre schon aktiv, ohne Sensor,
Sperre nicht übernommen, Komfort-Minimum, Feld 0 = wie bisher, andere Typen, Vorschlag, Dashboard, Config-Flow).

## Entwurf eines Kommentars für Issue 5 (nicht gepostet)

> **Entwurf zum Testen: vorsorgliche Sperre**
>
> Wie angekündigt kommt hier ein Entwurf, bevor die Version um den 13. Dezember erscheint. Er ist **standardmäßig aus** und
> greift nur bei Geräten vom Typ „Einstellung ändern“, bei denen du das neue Feld **Anlaufleistung** einträgst.
>
> **So funktioniert es:** Solange die Wärmepumpe nicht läuft und der Spielraum bis zur Grenze kleiner ist als die
> Anlaufleistung, hält der Wächter den Sperrkontakt auf dem Wert für „gesenkt“ (bei dir `on`). Sobald genug Spielraum da ist,
> gibt er sie frei. Eine vorsorgliche Sperre dauert nie länger als 30 Minuten (einstellbar), zwischen Sperre und Freigabe liegen
> mindestens 3 Minuten, und eine Wärmepumpe, die schon läuft, wird nie vorsorglich gesperrt.
>
> **Was du brauchst:** den Leistungssensor der Wärmepumpe (neues Feld beim Gerät) oder eine Entität, die „läuft“ anzeigt. Mit
> dem Leistungssensor zeigt der Status-Sensor nach ein paar Läufen die gemessene Anlaufspitze als Vorschlag.
>
> **Bitte zuerst beobachten:** Anlaufleistung eintragen und beim Gerät „Nur beobachten“ einschalten. Im Protokoll steht dann
> „hätte vorsorglich gesperrt …“ und beim echten Anlauf „eine Sperre hätte diesen Anlauf verschoben“. Wenn das passt,
> „Nur beobachten“ ausschalten.
>
> Uns interessiert: Startet deine Wärmepumpe nach der Freigabe zuverlässig (manche haben nach einer EVU-Sperre eine eigene
> Wartezeit)? Wie oft wird gesperrt, und kommt die Höchstdauer vor? Danke fürs Testen!
>
> ---
>
> **Draft for testing: precautionary lock**
>
> As announced, here is a draft before the release around 13 December. It is **off by default** and acts only on devices of
> type "change a setting" where you enter the new field **start power**.
>
> **How it works:** while the heat pump is not running and the headroom up to the limit is smaller than the start power, the
> guard keeps the lock contact at the value for "lowered" (`on` in your case). As soon as there is enough headroom, it frees it.
> A precautionary lock never lasts longer than 30 minutes (adjustable), there are at least 3 minutes between lock and release,
> and a heat pump that is already running is never locked in advance.
>
> **What you need:** the power sensor of the heat pump (new field at the device) or an entity that shows "running". With the
> power sensor the status sensor shows the measured start peak as a suggestion after a few runs.
>
> **Please observe first:** enter the start power and switch on "observe only" at the device. The log then says "would have
> been locked …" and, at a real start, "a lock would have put this start off". If that looks right, switch "observe only" off.
>
> We would like to know: does your heat pump start reliably after the release (some have their own waiting time after a
> utility lock)? How often is it locked, and does the maximum duration occur? Thanks for testing!
