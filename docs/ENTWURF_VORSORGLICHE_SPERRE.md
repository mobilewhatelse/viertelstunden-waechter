# Entwurf: Vorsorgliche Sperre vor dem Anlauf (Issue #5)

Stand: Entwurf zum Testen für die Version um den 13.12.2026, **Standard aus**. Zweig `sperre-entwurf`.

## Worum es geht

Eine Wärmepumpe mit EVU-Sperrkontakt (als Gerät vom Typ *Einstellung ändern* eingetragen, Sperrkontakt → `on`) zieht beim
Anlauf sofort 4 bis 5 kW. Liegt das Haus schon bei 5 bis 6 kW, ist die Viertelstunde praktisch sofort über der Grenze. Bisher
griff der Wächter erst ein, wenn die Wärmepumpe schon lief, und sperrte sie direkt nach dem Start wieder: ein kurzer Takt für
den Verdichter. Die vorsorgliche Sperre verhindert den Anlauf, solange er nicht passt, statt ihn danach abzuwürgen.

> **Wichtig: eigene Wiederanlauf- oder Mindeststillstandszeit der Wärmepumpe.** Viele Wärmepumpen starten nach dem Ende einer
> EVU-Sperre nicht sofort, sondern erst nach einer eigenen Wartezeit (oft 5 bis 20 Minuten, je nach Hersteller und Einstellung).
> Der Wächter kennt diese Zeit nicht und hat dafür bewusst **keine** Einstellung. Folge: Nach einer Freigabe kann der Spielraum
> schon wieder weg sein, wenn die Wärmepumpe endlich anläuft; jede vorsorgliche Sperre kann den Start zusätzlich um diese
> Wartezeit verschieben. Deshalb **zuerst im Beobachten-Modus testen** und im Protokoll prüfen, wie oft gesperrt würde.

## Funktionsweise

Alle 20 Sekunden, für jedes Gerät vom Typ *Einstellung ändern* mit einer Anlaufleistung größer 0:

- **Spielraum** = `min(erlaubt, Ziel) − Netzbezug` (Netzbezug als Mittel der letzten 60 Sekunden, wie bei der normalen
  Regelung). *Erlaubt* ist der Durchschnitt, der bis zum Ende der Viertelstunde noch passt, *Ziel* = Grenze − Sicherheitsabstand.
- **Sperren**, wenn das Gerät **nicht läuft** (Leistung unter *Läuft ab*, oder die *Läuft-Entität* ist aus) und der Spielraum
  **kleiner als die Anlaufleistung** ist. Gesperrt wird mit genau denselben Werten wie beim normalen Eingriff (Einstellung und
  *Wert für „gesenkt“* des Geräts, z. B. Sperrkontakt `on`).
- **Freigeben**, sobald der Spielraum **120 Sekunden lang ohne Unterbrechung** mindestens Anlaufleistung + 0,2 kW beträgt (wie
  die normale Regelung beim Zurückgeben: Herd und Wasserkocher takten). Die Prognose-Reserve (`reserve_kw`) geht bewusst nicht
  in den Spielraum ein. Zurückgestellt wird wie bei der normalen
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
| Tagesgrenze | 4 h | höchstens so viele Stunden vorsorglich gesperrt je Kalendertag (0 bis 24, 0 = keine Tagesgrenze) |

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
- **Tagesgrenze** (Standard 4 h je Kalendertag und Gerät): Ist sie erreicht, wird eine laufende vorsorgliche Sperre aufgehoben,
  einmal kommt der Hinweis „Tagesgrenze (4 h) erreicht, heute keine weitere vorsorgliche Sperre“, und bis Mitternacht wird nicht
  mehr vorsorglich gesperrt. Die Tagessumme wird wie der Merker gespeichert und überlebt einen Neustart; um Mitternacht beginnt
  sie neu (eine Sperre über Mitternacht zählt ihren Teil für jeden Tag). Nur beobachtete Sperren zählen getrennt und begrenzen
  die echten nie. Die normale Regelung (laufendes Gerät) ist davon nicht betroffen.
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

- **Verdichter-Takt und Wiederanlaufzeit:** Die Sperre selbst schaltet keinen laufenden Verdichter. Aber Freigabe und erneute
  Sperre vor dem Anlauf können die Steuerung der Wärmepumpe verwirren, und die eigene Wiederanlauf- oder Mindeststillstandszeit
  der Wärmepumpe (siehe Hinweis oben) kennt der Wächter nicht. Keine Einstellung dafür, deshalb zuerst beobachten.
- **EVU-Zeiten des Netzbetreibers:** Netzbetreiber erlauben die EVU-Sperre oft nur begrenzt (z. B. 3 × 2 Stunden am Tag). Die
  Tagesgrenze des Wächters zählt nur seine eigenen vorsorglichen Sperren, nicht die des Netzbetreibers und nicht die normale
  Regelung. Wer einen echten EVU-Kontakt mitbenutzt, sollte das mit dem Netzbetreiber und dem Hersteller klären. Im gemeldeten
  Fall simuliert ein Tasmota-Relais den Kontakt. Eine fremde oder echte EVU-Sperre fasst der Wächter nie an.
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
4. Achten auf: Wie oft und wie lange gesperrt? Startet die Wärmepumpe nach der Freigabe, und wie lange wartet sie dabei selbst?
   Kommen „Höchstdauer“ oder „Tagesgrenze“ häufig vor (dann Anlaufleistung zu hoch oder Grenze zu knapp)? Gab es trotzdem
   Viertelstunden über der Grenze?

Automatische Tests: `tests/test_vorsorge.py` (Haus 5,5 kW + Anlauf 5 kW → gesperrt, Haus 2 kW → frei nach 120 s anhaltendem
Spielraum, Höchstdauer, Mindestabstand, Tagesgrenze, Mitternacht, Tagessumme nach Neustart, Tagesgrenze 0/Standard, beobachtete
Sperren begrenzen die echten nicht, läuft schon, Beobachten, Nur beobachten, Neustart, fehlende Messwerte, EVU-Sperre schon aktiv, ohne Sensor,
Sperre nicht übernommen, Komfort-Minimum, Feld 0 = wie bisher, andere Typen, Vorschlag, Dashboard, Config-Flow).

## Kommentar für Issue 5 (nicht gepostet; Stand 22.11.: Sperre kommt als Beta mit 0.15.1 am 13.12.)

> **Vorsorgliche Sperre kommt als Beta mit Version 0.15.1 (um den 13. Dezember)**
>
> Wie angekündigt: Die vorsorgliche Sperre ist in der nächsten Version drin, als **Beta und standardmäßig aus**. Du brauchst nichts
> Besonderes zu installieren, nur das normale Update in HACS und einen Neustart. Sie greift nur bei Geräten vom Typ „Einstellung
> ändern“, bei denen du das neue Feld **Anlaufleistung** einträgst. Solange das Feld leer ist, ändert sich nichts.
>
> **So funktioniert es:** Solange die Wärmepumpe nicht läuft und der Spielraum bis zur Grenze kleiner ist als die Anlaufleistung,
> hält der Wächter den Sperrkontakt auf dem Wert für „gesenkt“ (bei dir `on`). Hält der Spielraum zwei Minuten lang, gibt er sie
> frei. Eine vorsorgliche Sperre dauert nie länger als 30 Minuten, zusammen höchstens 4 Stunden am Tag (beides einstellbar),
> zwischen Sperre und Freigabe liegen mindestens 3 Minuten, und eine Wärmepumpe, die schon läuft, wird nie vorsorglich gesperrt.
>
> **Wichtig:** Viele Wärmepumpen haben nach einer EVU-Sperre eine eigene Wiederanlauf- oder Mindeststillstandszeit. Die kennt der
> Wächter nicht; die Wärmepumpe startet dann nach der Freigabe erst später, und bis dahin kann der Spielraum wieder weg sein.
> Deshalb bitte **zuerst nur beobachten**.
>
> **So gehst du vor:**
> 1. Wächter in HACS auf 0.15.1 aktualisieren, Home Assistant neu starten.
> 2. Beim Gerät den Leistungssensor der Wärmepumpe (oder eine Entität, die „läuft“ anzeigt) und die **Anlaufleistung** eintragen.
>    Mit dem Leistungssensor zeigt der Status-Sensor nach ein paar Läufen die gemessene Anlaufspitze als Vorschlag.
> 3. Beim Gerät **„Nur beobachten“** einschalten. Im Protokoll steht dann „hätte vorsorglich gesperrt …“ und beim echten Anlauf
>    „eine Sperre hätte diesen Anlauf verschoben“.
> 4. Wenn das passt, „Nur beobachten“ ausschalten.
>
> Uns interessiert: Startet deine Wärmepumpe nach der Freigabe zuverlässig, und wie lange wartet sie dabei selbst? Wie oft wird
> gesperrt, und kommen Höchstdauer oder Tagesgrenze vor? Danke fürs Testen!
>
> ---
>
> **Precautionary lock arrives as a beta with version 0.15.1 (around 13 December)**
>
> As announced: the precautionary lock is in the next version, as a **beta and off by default**. There is nothing special to
> install, just the normal update in HACS and a restart. It acts only on devices of type "change a setting" where you enter the
> new field **start power**. While the field is empty, nothing changes.
>
> **How it works:** while the heat pump is not running and the headroom up to the limit is smaller than the start power, the guard
> keeps the lock contact at the value for "lowered" (`on` in your case). Once the headroom has held for two minutes, it frees it.
> A precautionary lock never lasts longer than 30 minutes, at most 4 hours a day in total (both adjustable), there are at least
> 3 minutes between lock and release, and a heat pump that is already running is never locked in advance.
>
> **Important:** many heat pumps have their own restart delay or minimum off time after a utility lock. The guard does not know
> it; the heat pump then starts later after the release, and by then the headroom may be gone again. So please **observe first**.
>
> **What to do:**
> 1. Update the guard in HACS to 0.15.1 and restart Home Assistant.
> 2. At the device enter the power sensor of the heat pump (or an entity that shows "running") and the **start power**. With the
>    power sensor the status sensor shows the measured start peak as a suggestion after a few runs.
> 3. Switch on **"observe only"** at the device. The log then says "would have been locked …" and, at a real start, "a lock would
>    have put this start off".
> 4. If that looks right, switch "observe only" off.
>
> We would like to know: does your heat pump start reliably after the release, and how long does it wait by itself? How often is
> it locked, and do the maximum duration or the daily limit occur? Thanks for testing!
