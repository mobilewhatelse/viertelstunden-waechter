# Changelog / Änderungen

Format: newest first. German version below each English block is a short summary in German.

## 0.15.0 - unreleased

- **Charts full width:** tap a chart on the dashboard and it opens on a page of its own in the dashboard, over the whole width, with its caption; held sideways it is large. The app is not loaded again, the back arrow leads back. **Create the dashboard again** to get it. Also: right after a restart a dashboard card no longer writes a template error to the log while its sensor is not back yet. *Deutsch:* Grafiken über die ganze Breite: Ein Tipp auf eine Grafik im Dashboard öffnet sie auf einer eigenen Seite im Dashboard, über die ganze Breite und mit ihrer Beschriftung; quer gehalten wird sie groß. Die App lädt dabei nicht neu, der Zurück-Pfeil führt zurück. **Dashboard neu erstellen**, damit es kommt. Außerdem: Direkt nach einem Neustart schreibt eine Dashboard-Karte keinen Template-Fehler mehr ins Protokoll, solange ihr Sensor noch nicht wieder da ist.
- **A counter step after a gap is no peak (issue #4):** if the import counter said nothing for longer than a quarter hour (the meter
  or its connection was away) and then brings the energy of the whole gap at once, the step is left out: the quarter hour goes on
  with what the power sensor measured and is not recorded as a peak. A counter that only rested because nothing was imported is
  not affected. The bound for a believable counter step now follows the own limit (four times the limit, at least 25 kW) instead
  of 60 kW for every house. **Action `correct_quarter` can also remove:** without a value the quarter hour is taken out of the
  record and the peaks are worked out again; described in the FAQ. *Deutsch:* Ein Zählersprung nach einer Lücke ist keine Spitze
  (Issue #4): Meldet der Bezugszähler länger als eine Viertelstunde nichts und bringt dann die Energie der ganzen Lücke auf
  einmal, zählt dieser Sprung nicht; die Viertelstunde läuft mit dem Wert des Leistungssensors weiter und wird nicht als Spitze
  verbucht. Ein Zähler, der nur ruht, weil nichts bezogen wurde, ist nicht betroffen. Die Grenze für einen glaubhaften
  Zählersprung richtet sich jetzt nach der eigenen Grenze (das Vierfache, mindestens 25 kW) statt 60 kW für jedes Haus. Die Aktion
  `correct_quarter` kann auch löschen: Ohne Wert wird die Viertelstunde aus der Aufzeichnung genommen und die Spitzen werden neu
  berechnet; beschrieben in den häufigen Fragen.
- **FAQ:** why the import can get above the limit although the guard runs, and which power sensor to enter for a wallbox (the
  whole power straight from the wallbox, not one phase, not the car's cloud). *Deutsch:* Häufige Fragen: warum der Bezug trotz
  Wächter über die Grenze kommen kann, und welcher Leistungssensor bei der Wallbox einzutragen ist (die gesamte Leistung direkt
  von der Wallbox, nicht eine Phase, nicht die Cloud des Autos).
- **evcc on its own connection:** the guard talks to evcc on a client session of its own (one per installation) instead of Home Assistant's
  shared one, so evcc's login cookie never reaches other integrations. *Deutsch:* evcc über eine eigene Verbindung: Der Wächter spricht mit
  evcc über eine eigene Sitzung statt über die gemeinsame von Home Assistant, das Anmelde-Cookie von evcc erreicht keine andere Integration.
  (The password fix of 0.14.5 is included. / Die Korrektur zum Passwort aus 0.14.5 ist enthalten.)
- **Bug report on request:** new button *Send bug report* next to the feedback (text optional). One press sends it, and the
  notification then shows exactly what was sent. It holds what is needed to find an error: version, mode, limit, the values of
  the running quarter hour, where the grid reading comes from and how old it is, per device the kind, whether it is being reduced,
  per setting its integration, model, firmware, the value now and its range, how fast and how often commands arrived or failed,
  whether the sensors deliver values, the last 20 log entries (only as a distance in hours) and the last 20 warnings of the guard.
  Names, entity ids, addresses, IP addresses and identifiers are removed first. Independent of *Share anonymous data*. Create
  the dashboard again to see the button in the card *Feedback*.
  *Deutsch:* Fehlerbericht auf Knopfdruck: neuer Knopf *Fehlerbericht senden* bei der Rückmeldung (Text optional). Ein Druck
  sendet ihn, die Benachrichtigung zeigt danach genau, was gesendet wurde. Er enthält, was zur Fehlersuche nötig ist: Version,
  Betriebsart, Grenze, die Werte der laufenden Viertelstunde, woher der Netzbezug kommt und wie alt er ist, je Gerät Art und ob
  gerade eingegriffen wird, je Einstellung Integration, Modell, Firmware, aktueller Wert und Bereich, wie schnell und wie oft Befehle
  ankamen oder fehlschlugen, ob die Sensoren Werte liefern, die letzten 20 Protokolleinträge (nur als Abstand in Stunden) und die
  letzten 20 Warnungen. Namen, Entitäts-IDs, Adressen, IP-Adressen und Kennungen werden vorher entfernt. Unabhängig von *Anonyme
  Daten teilen*. Dashboard neu erstellen, damit der Knopf in der Karte *Rückmeldung* erscheint.

- **Devices behind a cloud are no longer reported too early (from feedback):** the guard measures how often a device's power
  sensor delivers a new value while it draws power. If that takes longer than usual (e.g. a wallbox whose power comes through
  the manufacturer's cloud only every few minutes), it waits that long before it calls a command "not carried out", at most
  5 minutes. Before, it checked after one minute and reported a miss that was only a late report. The bug report shows the
  measured interval per device.
  *Deutsch:* Geräte hinter einer Cloud werden nicht mehr zu früh gemeldet (aus einer Rückmeldung): Der Wächter misst, wie oft
  der Leistungssensor eines Geräts einen neuen Wert liefert, während es Strom zieht. Dauert das länger als üblich (z. B. eine
  Wallbox, deren Leistung nur alle paar Minuten über die Cloud des Herstellers kommt), wartet er so lange, bevor er einen Befehl
  „nicht umgesetzt“ nennt, höchstens 5 Minuten. Bisher prüfte er nach einer Minute und meldete einen Fehler, der nur eine späte
  Meldung war. Der Fehlerbericht zeigt den gemessenen Abstand je Gerät.

- **Battery reserve: freeze at the current state of charge (from feedback):** with a minimum-SOC setting (e.g. Victron) enter
  `soc` as the value that keeps the charge. Before a forecast peak the minimum is set to the state of charge at that moment,
  rounded down (a minimum above it would make some inverters charge from the grid) and never below the value already set.
  *Deutsch:* Akku-Reserve beim aktuellen Ladestand einfrieren (aus einer Rückmeldung): Bei einer Mindest-SOC-Einstellung (z. B.
  Victron) als Wert `soc` eintragen. Vor einer erwarteten Spitze wird das Minimum auf den Ladestand in diesem Moment gesetzt,
  abgerundet (ein Minimum darüber lässt manche Wechselrichter aus dem Netz laden) und nie unter den schon eingestellten Wert.
- **Battery: minimum SOC follows the charge back up (from feedback, switch at the battery, default off):** after a release the
  minimum SOC is not set back at once (e.g. 15 -> 30 % with the battery at 20 %, which makes a Victron ESS charge from the grid),
  but to the state of charge, rounded down, and raised with it until the old value is reached. Stops if the value is changed by
  someone else; the old value comes back at once in observe mode, when switched off or when the integration is unloaded.
  *Deutsch:* Akku: Mindest-Ladestand folgt dem Ladestand zurück (aus einer Rückmeldung, Schalter beim Akku, Standard aus): Nach
  einer Freigabe wird das Minimum nicht auf einmal zurückgestellt (z. B. 15 -> 30 % bei 20 % Ladestand, ein Victron ESS lädt dann
  aus dem Netz), sondern auf den Ladestand, abgerundet, und mit ihm angehoben, bis der alte Wert erreicht ist. Endet, wenn jemand
  anderer den Wert ändert; im Beobachtungsmodus, beim Ausschalten oder Entladen der Integration kommt der alte Wert sofort zurück.
- **Battery: recharge from a time (from feedback, optional):** if PV has not reached the old minimum by the set time, it is set
  back and the battery charges from the grid, slowly with an optional setting (e.g. maximum charge current 40 A) that is put back
  when the old value is reached.
  *Deutsch:* Akku: Nachladen ab einer Uhrzeit (aus einer Rückmeldung, optional): Hat die PV den alten Mindest-Ladestand bis zur
  eingestellten Uhrzeit nicht erreicht, wird er zurückgestellt und der Akku aus dem Netz nachgeladen, langsam mit einer optionalen
  Einstellung (z. B. maximaler Ladestrom 40 A), die zurückkommt, wenn der alte Wert erreicht ist.
- **Battery, step of the minimum SOC (from feedback):** new optional field *Step of the minimum SOC*. Some integrations report a
  coarse step (Victron ESS 5 %) although the battery takes every whole percent; with `1` the minimum follows 20, 21, 22 … instead of
  20, 25, 30. For any battery. *Deutsch:* Neues optionales Feld *Schrittweite Mindest-Ladestand*: Melden Integrationen einen groben
  Schritt (Victron ESS 5 %), obwohl der Akku jedes ganze Prozent annimmt, folgt das Minimum mit `1` in 1-%-Schritten. Für jeden Akku.
- **Battery, details for these three:** the minimum is always set in whole percent (a Victron takes no decimals). A device that
  reports a new value late is waited for up to two minutes before the value counts as changed by someone else.
  *Deutsch:* Akku, Details zu diesen drei: Das Minimum wird immer in ganzen Prozent gesetzt (ein Victron nimmt keine
  Nachkommastellen). Meldet ein Gerät einen neuen Wert verspätet, wartet der Wächter bis zu zwei Minuten, bevor der Wert als von
  jemand anderem geändert gilt.
- **Slow commands are no longer cut off (also in 0.14.4):** after 15 s without an answer Home Assistant cancelled the command, so a
  device that always needs longer (a car waking up, a wallbox through its cloud) never got one. Now the command goes on in the
  background, the log says "device answers slowly", and a later error is logged too.
  *Deutsch:* Langsame Befehle werden nicht mehr abgebrochen (auch in 0.14.4): Nach 15 s ohne Antwort brach Home Assistant den
  Befehl ab, ein Gerät, das immer länger braucht (Auto beim Aufwecken, Wallbox über die Cloud), bekam so nie einen. Jetzt läuft der
  Befehl im Hintergrund weiter, das Protokoll sagt „Gerät antwortet langsam“, ein späterer Fehler wird auch protokolliert.
- **Charge plan: a failed command is no longer sent every 20 s (from feedback):** after a failed pause the next try comes after
  5 minutes, after a failed resume after 1 minute. The log says what went wrong, e.g. "no answer within 15 s", instead of empty
  brackets; this applies to all error lines.
  *Deutsch:* Ladeplan: Ein fehlgeschlagener Befehl wird nicht mehr alle 20 s gesendet (aus einer Rückmeldung): Nach einer
  fehlgeschlagenen Pause kommt der nächste Versuch nach 5 Minuten, nach einer fehlgeschlagenen Freigabe nach 1 Minute. Das
  Protokoll sagt, was schiefging, z. B. „keine Antwort innerhalb von 15 s“, statt leerer Klammern; das gilt für alle Fehlerzeilen.
- **Vehicle: unused field removed (from feedback):** the vehicle dialog showed an unlabelled field "allow_entity" that the charge
  plan never used. A value already entered there is ignored as before.
  *Deutsch:* Fahrzeug: unbenutztes Feld entfernt (aus einer Rückmeldung): Der Fahrzeug-Dialog zeigte ein unbeschriftetes Feld
  „allow_entity“, das der Ladeplan nie benutzt hat. Ein dort schon eingetragener Wert wird wie bisher nicht beachtet.

- **Sharing, new text:** the weekly statistic now uses a random id that changes every month (the fixed id of older versions is
  deleted on the service once), plus how long the guard has been running as a rough class. With the text of 0.15 (the same
  confirmation as for the device check) also the peak of the last month with and without the guard and the interventions of the
  last 30 days, only as rough classes. The text names every purpose, also summaries passed on to research or partners, always
  from at least 10 installations. The service keeps the weekly data at most 60 days.
  *Deutsch:* Teilen mit neuem Text: Die Wochenstatistik hat jetzt eine zufällige Kennung, die jeden Monat wechselt (die feste
  Kennung früherer Versionen wird am Dienst einmal gelöscht), dazu grob, wie lange der Wächter schon läuft. Mit dem Text von 0.15
  (dieselbe Bestätigung wie für den Geräte-Check) auch die Spitze des letzten Monats mit und ohne Wächter und die Eingriffe der
  letzten 30 Tage, nur als grobe Klassen. Der Text nennt alle Zwecke, auch Zusammenfassungen für Forschung oder Partner, immer aus
  mindestens 10 Installationen. Der Dienst behält die Wochendaten höchstens 60 Tage.

- **Device check (only with *Share anonymous data*):** once a day the guard asks our service whether the connected devices still work
  as usual. Wallbox: charging power against set current and phases (drop in power, a missing phase, a slow trend); home battery:
  usable capacity from full swings of at least 40 points; switches, pumps, water heaters: power while running ("needs more than
  usual", "draws nothing although on"); heat pump: daily energy against outdoor temperature; water heater: daily energy against its
  own mean. The guard only measures; the thresholds and the judging live on the service, so they can improve without an update.
  The request carries "days ago" instead of dates, device numbers valid only within one request, no names, entity ids or id of the
  installation; the service answers and keeps only anonymous rows of finished days. Nothing is switched, the check only tells.
- **Comparable with the same devices of others (for later):** the anonymous rows also carry values that do not depend on the size
  of the house: a home battery's capacity in percent of its own base value, its rated capacity and age in half years; a heat
  pump's day against its own curve at the same outdoor temperature and the shape of that curve (0 against 10 deg C); a water
  heater's day against its own mean.
- **How it shows:** a sensor *Device check* (ok, hint, warn, learning, none, sharing off, confirm) with the result per device as an
  attribute, a card in the statistics view of the dashboard, a warning once under Repairs and, if *Notify on intervention* is on, as a
  notification.
- **New optional fields per device:** *Power of the battery* (home battery, needed for the capacity) and *Kind of device* (heat pump,
  water heater/heating rod, pump, other) for switches, settings, throttle and scripts. Manufacturer and model come from the device list
  of Home Assistant.
- **Shared before 0.15?** One quiet entry under Repairs asks to confirm the device check once (preset to keep sharing). Until then the
  weekly statistics go on as before and the device check sends nothing. Switching *Share anonymous data* on, or choosing it in the
  set-up, counts as the consent.

*Deutsch:* Geräte-Check einmal am Tag (nur mit *Anonyme Daten teilen*): Wallbox, Hausakku, schaltbare Geräte, Wärmepumpe und Boiler;
der Wächter misst nur, beurteilt wird auf unserem Dienst. Sensor, Karte, Reparatur-Meldung; neue Felder *Leistung des Akkus* und
*Art des Geräts*. Wer schon geteilt hat, bestätigt den Geräte-Check einmal unter Reparaturen; bis dahin sendet er nichts.
Für den späteren Vergleich mit gleichen Geräten zusätzlich Werte, die nicht von der Hausgröße abhängen (Akku in Prozent vom
Anfangswert, Nennkapazität, Alter; Wärmepumpe und Boiler gegen den eigenen üblichen Wert).

## 0.14.5 - 2026-11-17

Security fix.

- **The evcc password is no longer shown:** with an evcc loadpoint that has a password, the password was in the attribute
  `configuration` of the status sensor and in the downloaded diagnostics. It was never sent anywhere and never written to the
  database. Now settings with a password, token or secret are left out. If you shared a diagnostics file with an evcc password,
  change the password in evcc.

*Deutsch:* Sicherheitskorrektur: Bei einem evcc-Ladepunkt mit Passwort stand das Passwort im Attribut `configuration` des
Status-Sensors und in der heruntergeladenen Diagnose. Es wurde nie gesendet und nicht in die Datenbank geschrieben. Jetzt fehlen
Einstellungen mit Passwort, Token oder Geheimnis dort. Wer eine Diagnosedatei mit evcc-Passwort geteilt hat: Passwort in evcc ändern.

## 0.14.4 - 2026-11-15

Fix for devices that answer slowly, e.g. a car or wallbox through its cloud.

- **Slow commands are no longer cut off (from feedback):** the guard waited at most 15 s for a command and then Home Assistant
  cancelled it, so a device that always needs longer (a car that has to wake up, a wallbox through its cloud) never got a command:
  neither the lowering of the charging current nor the pause of the charge plan. Now the guard still waits at most 15 s, but the
  command goes on in the background; the log says "device answers slowly", and an error that comes later is logged too.
- **Charge plan:** a slow command counts as sent. A command that really failed is tried again after 5 minutes (pause) or 1 minute
  (resume) instead of every 20 s.
- **Log:** errors say what went wrong, e.g. "no answer within 15 s", instead of empty brackets.

*Deutsch:* Fix für Geräte, die langsam antworten, z. B. Auto oder Wallbox über die Cloud. Der Wächter wartete höchstens 15 s auf
einen Befehl, danach brach Home Assistant ihn ab, so bekam ein Gerät, das immer länger braucht, nie einen Befehl (weder das Senken
des Ladestroms noch die Pause des Ladeplans). Jetzt wartet er weiter höchstens 15 s, der Befehl läuft aber im Hintergrund weiter;
das Protokoll sagt „Gerät antwortet langsam“, ein späterer Fehler wird auch protokolliert. Ladeplan: ein langsamer Befehl gilt als
gesendet, ein wirklich fehlgeschlagener wird nach 5 Minuten (Pause) bzw. 1 Minute (Freigabe) erneut versucht statt alle 20 s.
Fehlertexte sagen, was schiefging, statt leerer Klammern.

## 0.14.3 - 2026-11-14

Small things: wallboxes with the charging current as a list, the car's target from a list, and the current grid import in the dashboard.

- **Grid import now (from feedback):** the dashboard shows the grid import at this moment as a tile right below the status, in the
  overview and in the view *Today*. Create the dashboard again to get it (developer tools > actions > *Create dashboard*).
- **Wallbox with a list of currents:** the field *Charging current setting* now also takes a `select`. The guard reads the amps from
  the entries and picks the matching one, never a higher one; it lowers and raises step by step as with a number. If the list starts above the
  minimum current you set (list from 8 A, minimum 6 A), its lowest entry counts as the minimum. Tested in the
  simulator and in a test Home Assistant with a list like the Anker SOLIX V1, not on the real device (reports welcome).
- **Target of the car from a list (from feedback):** the field *Target from a sensor* now also takes a `select`, e.g. the target
  charge of Fordpass (shown as "80%"). Values like "80", "80%" or "80.0" are read; "Unsupported" counts as no value, then the fixed
  target applies. Tested with such a list in a test Home Assistant, not with a real Ford (reports welcome).
- **FAQ:** questions users really asked, with short answers: [docs/FAQ.md](docs/FAQ.md), German [docs/HAEUFIGE_FRAGEN.md](docs/HAEUFIGE_FRAGEN.md).
  With two short videos: creating the dashboard, and adding a wallbox with a list.

*Deutsch:* Kleine Dinge. **Netzbezug jetzt (aus einer Rückmeldung):** Das Dashboard zeigt den aktuellen Netzbezug als Kachel
direkt unter dem Status, in der Übersicht und in der Ansicht *Heute*. Dafür das Dashboard neu erstellen. **Wallbox mit Auswahlliste**
(„6 A“, „8 A“ …, z. B. Anker SOLIX V1): Das Feld *Einstellung Ladestrom* nimmt jetzt auch eine solche Liste; der Wächter wählt den
passenden Eintrag, nie einen höheren, und drosselt stufenweise wie bei einer Zahl. Beginnt die Liste über dem
eingestellten Mindeststrom (Liste ab 8 A, Mindeststrom 6 A), gilt ihr kleinster Eintrag als Mindeststrom. Getestet im Simulator und in einem Test-Home-Assistant
mit einer Liste wie bei der Anker SOLIX V1, nicht am echten Gerät (Rückmeldungen willkommen). **Ziel des Autos aus einer Auswahlliste (aus einer Rückmeldung):** Das Feld *Ziel aus einem Sensor* nimmt jetzt auch eine Liste,
z. B. den Ziel-Ladestand von Fordpass („80%“); „Unsupported“ zählt als kein Wert, dann gilt das feste Ziel. Getestet mit so einer
Liste im Test-Home-Assistant, nicht mit einem echten Ford. Neu: **Häufige Fragen**
([docs/HAEUFIGE_FRAGEN.md](docs/HAEUFIGE_FRAGEN.md)) mit zwei kurzen Videos: Dashboard anlegen und Wallbox mit Liste hinzufügen.

## 0.14.2 - 2026-11-13

**From feedback:** "Switched to *Active*, the guard says it would lower the Wattpilot, but nothing happens." The cause: besides the
mode (*Observe only* / *Active*) every device has its own switch *Observe only*. With it on, the guard never touches that device,
also in the mode *Active*; it only writes to the log what it would have done. Two switches with nearly the same name - easy to miss.

- **New hint under Settings > Repairs:** with the mode *Active* and a device still on *Observe only*, the guard names the device.
  *Fix* switches *Observe only* off there with one click; *Ignore* keeps it, for a device you want to watch on purpose.
- **Clearer log line:** "... nothing was sent (Observe only is on at the device)".
- **Dashboard from the developer tools:** the response of *Create dashboard* is now the dashboard itself. Copy all of it and paste it
  into the raw configuration editor. Before, the response also held a `yaml:` part, and pasting all of it gave an error.
- The switch in the dashboard is called *Share anonymous data*, as the entity.

*Deutsch:* **Aus einer Rückmeldung:** „Auf *Aktiv* umgeschaltet, der Wächter sagt, er würde den Wattpilot drosseln, aber es passiert
nichts.“ Der Grund: Neben der Betriebsart (*Nur beobachten* / *Aktiv*) hat jedes Gerät einen eigenen Schalter *Nur beobachten*. Ist
er an, greift der Wächter bei diesem Gerät nie ein, auch nicht in der Betriebsart *Aktiv*; er schreibt nur ins Protokoll, was er tun
würde. **So beheben Sie es (auch ohne Update):** Einstellungen > Geräte & Dienste > Viertelstunden-Wächter > beim Gerät (z. B.
„Wallbox · … · nur beobachten“) die drei Punkte > *Neu konfigurieren* > *Nur beobachten* ausschalten > Absenden.
Neu in 0.14.2: Steht die Betriebsart auf *Aktiv* und ein Gerät noch auf *Nur beobachten*, erscheint unter Einstellungen > Reparaturen
ein Hinweis mit dem Gerätenamen; *Reparieren* schaltet *Nur beobachten* mit einem Klick aus. Die Protokollzeile sagt jetzt dazu „beim
Gerät ist ‚Nur beobachten‘ an“. **Dashboard:** Die Antwort von *Dashboard erstellen* in den Entwicklerwerkzeugen ist jetzt das
Dashboard selbst – alles kopieren und in den Rohkonfigurationseditor einfügen. Bisher stand darin zusätzlich ein Teil `yaml:`, und wer
alles eingefügt hat, bekam einen Fehler. Der Schalter im Dashboard heißt jetzt *Anonyme Daten teilen*.

## 0.14.1 - 2026-11-12

- **House forecast without the car for charge planners:** the sensor *expected peak in 24 h* gets the attribute `hours_house`
  (the house alone: no wallbox, no running charge, no car plan). `hours` stays as it is (the guard's own view with the expected charging).
  A charge planner such as Plugwhen must not count the car it plans as load, otherwise it finds "no room" every night.
- **First fill of the forecast without the wallboxes:** the hourly statistics of the grid import get the mean power of every wallbox
  (and evcc loadpoint) with a power sensor taken off, so the house model no longer learns the charging of the car as house load.
- **Rebuilt once:** a house model from an earlier version is filled again on the first start (statistics without the wallboxes, then
  the quarter hours measured here, wallbox taken off). Nothing to do.
- **Short README:** the README is down to the essentials; the full text is now the manual in `docs/MANUAL.md`.
- **Question about sharing anonymous data, said more precisely:** from 0.15 the device check is done by our service, once a day and
  only with *Share anonymous data*; without it there is no device check, everything else stays local. The text now lists what 0.15 will
  send for the check, and the preview no longer says "runs locally, no cloud".

*Deutsch:* Kurzes README, der volle Text steht jetzt als Handbuch in `docs/MANUAL.md`. Eigene Hausprognose ohne Auto (`hours_house`) für Lade-Planer wie Plugwhen; die Startbefüllung aus der Statistik zieht die
Wallboxen ab; das Hausmodell wird beim ersten Start einmal neu aufgebaut. Die Frage zur Datenfreigabe sagt jetzt genau, dass der
Geräte-Check ab 0.15 über unseren Dienst läuft und nur mit Datenfreigabe; die Vorschau sagt nicht mehr „läuft lokal, ohne Cloud“.

## 0.14.0 - 2026-11-12

- **Share anonymous data, voluntary (default off), one switch:** asked in the last step of the set-up (and once under Repairs after
  the update), with a small animated preview of the coming device check (served by the integration itself, nothing loaded from
  outside); afterwards the switch *Share anonymous data*. Today it sends the weekly usage statistics: a random id, versions, country and
  language, kinds of devices and the integrations their entities come from; never names, entity ids, measurements or passwords;
  switching off requests deletion. The consent already covers anonymous daily values of the devices (energy, highest power, running
  time, outdoor temperature, manufacturer and model; without date, time of day or any id), which a later version sends for the device
  check, so nobody has to be asked twice. **Feedback:** a text field and a button on the device, and the action `send_feedback`.
- **Service `correct_quarter`:** a quarter hour recorded wrong gets the value from the meter; the day's and the month's peak are
  worked out again from the recorded quarter hours (an older real peak outside the record is never removed) and a line goes to the log.
- **Fix: a reload or restart in the middle of a quarter hour could record a peak that never happened.** When it stops, the guard gives
  everything back (the wallbox to full power); when it started again it took the power of that moment for the whole quarter hour so
  far. Seen: 10.8 kW recorded as the month's peak, "limit cannot be kept" sent and the wallbox set to 6 A, while the meter counted
  8.4 kW. Now the running quarter hour is saved on stop and continued on start - exactly with the import counter (it kept counting
  while the guard was away), else the saved energy plus the gap. A quarter hour that really has to begin with a guess (first start,
  nothing saved) is still handled carefully, but it is not recorded as a peak, not learned, and sends no "limit cannot be kept".
- **A running charge is in the forecast:** a car that charges right now stays in the 24-hour forecast until its probable end (the
  energy missing up to the car's limit at the present power; two hours if state of charge or capacity are unknown). Before, an
  evening charge showed 0.4 kW in the forecast while the wallbox drew 8.6 kW, because the learned pattern had no charging there.
  Attribute `running_charge` (power, until). The forecast is never lowered by it.
- **An executed plan covers the car until the next need:** when the planner switches the wallbox by its plan and its look-ahead says
  that nothing has to be charged before a later day, the learned wallbox pattern does not count until then (before: only until the
  next departure). A plan that only recommends changes nothing, the car may then charge whenever it is plugged in.
- **Fix: one wallbox entered twice was counted twice.** A wallbox entered directly and, set to observe only, as an evcc loadpoint
  was added up (17 kW instead of 8.5 kW) for learning the house without the wallbox. An observed device with nearly the same power
  as a real wallbox now counts once.
- **Set-up with evcc, three gaps closed:** an evcc without a grid meter is still found for its loadpoints (before, the assistant offered
  no evcc loadpoint then); a loadpoint that is a heating device in evcc (heat pump, heating rod) is not offered and refused with a clear
  message; a password is tried when saving (evcc answers its state without a login, so a wrong password only showed at the first
  intervention).
- **Observe only says the real step for a wallbox or an evcc loadpoint:** the note named the whole lever ("lowered by 6.5 kW", down
  to the minimum) although only 2.0 kW were too much. Now it says what the guard would set: "limited from 16 A to 12 A (−2.0 kW)",
  the same arithmetic as for a real wallbox.
- **Set-up assistant:** adding the integration is now four short steps instead of one long page: grid import (a sensor and/or evcc,
  a local evcc is filled in), *is the sign right?* (current value and a check of the last nights), the limit (with the highest quarter
  hour of the last days as a hint), the devices that matter most (evcc loadpoint or wallbox) - then finish. Everything else stays on the
  integration page.
- **Turn the sign round** for the grid sensor (set-up and settings) and for the power sensor of every device: a meter that counts
  import as negative needs no template sensor any more. The set-up proposes it when the sensor was negative at night (no sun, so it
  must be import); a device dialog says so when a consumer shows nearly only negative values.
- **evcc loadpoint taken over:** the dialog lists evcc's loadpoints by name and takes name, minimum and maximum current and whether the
  charger can switch phases from evcc.

  *Deutsch:* Einrichtungsassistent in vier Schritten; „Vorzeichen umkehren“ für Netzbezug und Geräte, mit Erkennung aus der Nacht;
  evcc-Ladepunkt mit Name, Strömen und Phasen aus evcc übernommen.
- **An unplugged car is planned from the second hour on:** before, a car that was not plugged in was left out of the 24-hour forecast
  completely, although it is often plugged in later that day (expected peak 1 kW in the morning, 9 kW in the afternoon). Now the first hour
  is the house alone (the car cannot charge right now), after that the learned wallbox pattern counts. A full car stays out. Attribute
  `vehicle_included` says `after_1h` then.
- **Fix:** a reload of the guard (for example after a change in the settings) within five minutes after a quarter hour lost the
  last quarter hours of the CSV export and of the learned model; both are saved on unload now. Found by an installation test that failed once.
- **Shelly 3EM Pro confirmed:** a user set the guard up with a template sensor for the grid import of a real Shelly 3EM Pro and ran it
  for 24 h with 0.13.3 (issue 1). README and guide say so now.
- **Little to set with evcc:** an evcc on the same machine as Home Assistant (add-on) is found and its address suggested at set-up
  (only if it reports a grid meter) and for a new evcc loadpoint; a loadpoint takes address and password from the general settings.
  Suggested only, nothing is saved unless the form is saved with it; an evcc elsewhere on the network is entered as before.
  *Deutsch:* Ein evcc auf demselben Rechner wird bei der Einrichtung vorgeschlagen; ein evcc-Ladepunkt übernimmt Adresse und
  Passwort aus den allgemeinen Einstellungen.
- **A charge plan that nobody executes no longer lowers the forecast.** With a car planner chosen, the plan replaced the learned
  wallbox pattern until departure, also when the planner only recommends (Plugwhen in learn mode): "not needed" took the car out of
  the forecast although it charged when plugged in (expected peak 2.5 kW, real 9.1 kW). Now the plan says so (attribute
  `executed: false`), and the higher of the plan and the usual view counts; attribute `car_plan.executed`. A plan without the
  attribute counts as executed, as before.
  *Deutsch:* Ein Ladeplan, den niemand ausführt (Lernmodus), senkt die Prognose nicht mehr; es zählt der höhere Wert aus Plan und
  gelerntem Wallbox-Muster.
- **evcc loadpoint** (new device type, experimental): a wallbox that evcc controls. The guard sets the loadpoint's maximum current
  (a ceiling, evcc keeps regulating below it), works with the current evcc offers right now and gives back the original ceiling,
  also after a restart. Charging is never stopped, evcc's mode is not touched. Only the address of evcc is needed (password if evcc
  asks for one); the connection and the loadpoint are checked when saving. Tested against a demo evcc 0.319.0, not on hardware.
  *Deutsch:* neuer Gerätetyp evcc-Ladepunkt (experimentell): der Wächter setzt die Obergrenze des Ladestroms in evcc und gibt die
  ursprüngliche zurück.
- **Grid import from evcc** (optional, general settings): the entered sensor always wins; evcc is used without a sensor, or as a
  reserve (switch, default on) while the sensor has no usable value. Never averaged; a clear difference of the grid import (over 0.3 kW and 15 % for
  two minutes; export counts as 0 on both sides) is noted once in the log. Attributes `grid_source`, `grid_evcc_kw`, `sources_differ` on the status sensor.
  The grid import sensor is now optional when evcc is entered. *Deutsch:* Netzbezug aus evcc, der eigene Sensor gilt zuerst,
  evcc als Reserve, nie gemittelt, Abweichungen werden gemeldet.
- **Card Sources compared** in the generated dashboard, only with an evcc address: your sensor and evcc as bars, which one counts,
  warnings. *Deutsch:* Karte Quellen im Vergleich, nur mit evcc.
- **Observe only per device** (switch in every device): the guard writes what it would do with the device, sends nothing and does not
  count it as a lever. *Deutsch:* Nur beobachten je Gerät.
- **Warning for a wallbox entered twice:** a Wallbox device and an evcc loadpoint charging with nearly the same power for two minutes are
  noted once in the log (attribute `wallbox_twice`). *Deutsch:* Warnung, wenn eine Wallbox doppelt eingetragen scheint.
- Installation tests: new `tests/install/itest_evcc.py` (with a demo evcc); `itest.py` no longer runs itself when imported;
  the simulated grid sensor changes every minute so that it never counts as stale.

- **Weather correction of the load forecast** (switch, default on; needs a weather entity or an outdoor temperature sensor in
  the general settings, otherwise nothing changes): samples remember the outdoor temperature, two slopes (heating below
  15 C, cooling above 22 C, never negative, at least 14 days) are fitted from whole days, and the forecast moves each
  sample to the expected temperature. Temperature history of the sensor is read once. Attribute `weather` on the forecast
  sensor. Also used by *Throttle ahead* and the charge plan. *Deutsch:* Wetterkorrektur der Lastprognose (Heizen im Winter,
  Klimaanlage im Sommer), Schalter standardmäßig an, wirkt nur mit Wetter-Entität oder Außentemperatur-Sensor.
- **Charge plan of a car planner as an optional input** (general settings): you choose the car planner (for example Plugwhen) and the
  guard finds the charge plans of all its vehicles by itself; other sensors can be named by hand. Until the departure the forecast is
  the house plus the planned car load instead of the learned wallbox pattern. Without a plan nothing changes. Attribute `car_plan`
  on the forecast sensor. Tested with both integrations in one Home Assistant.
- **Dashboard with a car planner:** when a car planner is chosen in the general settings, *Create dashboard* shows the
  planner's charge plan (per vehicle: plan sensor, *Ready for departure* if the planner has one, windows with energy, highest
  power and share from the sun) instead of the guard's own plan, plus the line *Car plan in the forecast* (connected, windows,
  until when). **Either the planner or the guard:** with a car planner the guard's own plan and its switches are not on the dashboard
  at all (one plan instead of two that disagree; they stay on the device page). Without a planner the dashboard is unchanged. Planners are found by unique id (charge plan and readiness sensors of the chosen entry) or
  taken from *Other charge plan sensors*; nothing of the planner is imported. New documentation section *The guard and a car
  planner together* (roles, last word stays with the guard, one plan instead of two). *Deutsch:* Mit gewähltem Auto-Planer zeigt
  das Dashboard dessen Ladeplan statt des eigenen, mit Zeile "Auto-Plan in der Prognose"; neuer Abschnitt "Wächter und
  Auto-Planer zusammen". Ohne Planer bleibt alles wie bisher.
- **Weather card says only what it knows:** until the correction can say something (fewer than 14 whole days with temperature, or a
  slope of zero) the card is one line, *Weather correction: still learning, 3 of 14 days with temperature*; the numbers (heating,
  cooling, fit in kW per kelvin) appear once it is active. *Deutsch:* Wetterkarte zeigt nur "lernt noch", bis sie etwas aussagen kann.
- **Dashboard cleaned up, graphics first** (user feedback): fewer cards; settings and features stay. Left out: the explanation text,
  the table of devices and priorities, intermediate tiles (allowed now, quarter hour so far, last quarter hour, without the guard,
  relief now), the tables of daily peaks, months and interventions (the charts show them), the 3-day statistics graph. The explanation
  of the day only shows while the AI explainer is on. Titled cards have no header toggle (it flipped all switches at once).
- Documentation: HACS is the built-in **Marketplace** since Home Assistant 2026.11; installation texts and tables say so
  (catalog, `hacs.json` and the validation keep their names). *Deutsch:* HACS heißt seit 2026.11 Marketplace.
- **Maximum age of the grid reading** (setting, default 120 s, 0 = off): a reading that was not written for longer counts as
  missing (no interventions, everything given back after 90 s, status *no data*). Protects against sensors that only update every
  few minutes. Attributes `grid_age_s` and `grid_stale` on the status sensor. *Deutsch:* Höchstalter des Netzbezug-Messwerts.
- Dashboard (view *Statistics and forecast*): new card *Weather correction* with the switch and what is learned (temperature, hours of forecast, days, slopes, fit).
- Roadmap (documentation only): a smarter house forecast (weather, temperature, solar forecast) is noted as planned.
- Documentation only: README status and installation text updated (now in the HACS default list), new section *Support and
  feedback*, issue template *Bug report*, outdated dashboard-URL notes removed from README and guide.

## 0.13.3 - 2026-11-08

- **Fix (issue 1):** grid power, grid energy and the power sensor of a device can be **any sensor**, also a template sensor with the unit
  `W` but without `device_class: power` (for example one built from the three phases of a Shelly 3EM Pro). Before, such sensors were missing
  from the list. Instead of the device class the dialog now checks the **unit** when saving (W, kW, MW for power; Wh, kWh, MWh for energy)
  and says what to add if it is missing. Covered by the installation test with an equivalent simulated sensor; not tested with a real Shelly
  device here.

Deutsch: Netzbezug, Bezugszähler und die Leistungssensoren der Geräte können **jeder Sensor** sein, auch ein Template-Sensor mit der Einheit W
ohne Geräteklasse (z. B. aus den drei Phasen eines Shelly 3EM Pro). Statt der Geräteklasse prüft der Dialog beim Speichern die Einheit.

## 0.13.2 - 2026-11-03

- **Security (review by the HACS team):** the service `create_dashboard` no longer writes into dashboards. It only builds the
  dashboard and returns it as YAML (response key `yaml`, also as a notification) to paste into the raw configuration editor of a
  new dashboard. Before, it could replace all views of any storage dashboard, including ones the integration never created.
  The `dashboard` field is gone.
- All services (`create_dashboard`, `import_history`, `send_week_report`, `export_csv`, `explain_today`) are now registered as
  administrator services: a non-admin user can no longer call them; automations and scripts are not affected.
- The response of `create_dashboard` also contains the dashboard as `config` (the same content as the YAML).
- README and guide: installation leads with searching for the integration in HACS; adding a custom repository is the fallback
  until it is in the default list. The dashboard section explains how to paste the YAML.

Deutsch: `create_dashboard` schreibt nicht mehr in bestehende Dashboards, sondern liefert nur das YAML (auch als Meldung).
Alle Dienste dürfen nur noch Administratoren aufrufen (Automationen und Skripte nicht betroffen).

## 0.13.1 - 2026-10-28

- Dashboard: the explanation of the day now shows its date. An older explanation is labelled "Explanation of 27.10."
  with the hint that today's follows at 21:00, so it can no longer pass for today's. The fixed sentence on days without
  interventions names the day ("On 27.10. the guard did not need to intervene"). An error (for example no AI task chosen) is shown on the card.

## 0.13.0 - 2026-10-27

- **House and car apart:** with a wallbox the forecast learns the house and the wallbox separately; a full or unplugged
  car is left out of the forecast, the risk windows, *Throttle ahead* and *Battery reserve*. The charge plan no longer
  counts the car twice.
- **Battery reserve before a peak** (switch, default off): holds the battery with a configurable setting before a
  forecast risk window and puts the previous value back afterwards.
- **CSV export** (service `export_csv`): quarter-hour load profile (120 days) or daily peaks (400 days), standard or
  German Excel format, written to `config/viertelstunden_waechter/export/`.
- **AI explainer** (switch, default off, off after restart): daily explanation of the interventions via a Home
  Assistant AI task entity, sensor *Explanation of the day*, service `explain_today`; at most 4 AI calls per day.
- **Dashboard view *Today*** for the phone: status, forecast bar against the target, mode switch, peaks, the quarter
  hours of today, the latest log lines and the explanation of the day (one column, standard cards only).
- Charts of quarter hours and daily peaks: every bar is at least 2 pixels high, so a quiet day does not look empty.
- **English log lines and messages:** the guard's own texts follow the Home Assistant language (German or English).

*Deutsch:* Haus und Auto in der Prognose getrennt (volles oder nicht angestecktes Auto zählt nicht), Akku-Reserve vor einer
Spitze (Standard aus), CSV-Export, KI-Erklärer (Standard aus); Protokoll und Meldungen auch auf Englisch; neue Dashboard-Ansicht *Heute* fürs Handy.

## 0.12.1 - 2026-10-25

- Dashboard: the tile *Next risk* showed "Unknown" when no risk window is expected. It is now a text card: "none in the
  next 24 hours", or day, time window and expected peak (the sensor itself is unchanged).

## 0.12.0 - 2026-10-25

- **Throttle ahead by the forecast** (switch, default off): in a forecast risk quarter hour the guard keeps a reserve
  free and lowers the wallbox current and throttles early; it never switches a device off and never switches to 1 phase
  because of a forecast.
- Message on intervention lists every step of the first intervention and sends a summary when everything is given back.
- hassfest fixes: `energy` in `after_dependencies`, no braces in service texts, sorted manifest keys. `hacs.json`
  requires Home Assistant 2026.3.0.
- Installation test in Docker (`tests/install`).

*Deutsch:* Vorausschauend drosseln nach Prognose (Schalter, Standard aus); Meldung bei Eingriff mit allen Schritten und
Zusammenfassung; hassfest-Korrekturen; Installationstest.

## 0.11.0 / 0.11.1

- **Confirmation of commands:** every real intervention is read back after about 60 seconds; repeated once, then
  reported, and the device is left alone for 10 minutes so the next lever is used.
- Early warning (switch, default off), weekly report (switch, Monday 07:00, sensor and service `send_week_report`).

*Deutsch:* Rückmeldung nach jedem Befehl, Vorwarnung (Standard aus), Wochenbericht.

## 0.10.x

- Service `import_history`, `peaks_by_day` (400 days), large attributes are not stored in the database.
- Statistics view with SVG charts (forecast, weekly profile, daily peaks, months); colour scale per panel.

## 0.9.x

- **Charge plan for the car** (solar forecast of the Energy dashboard optional, executing it is a switch, default off).
- Nothing installation-specific in the code: mains voltage, charging efficiency and currency come from the
  Home Assistant configuration.

## 0.8.0

- Ready-made dashboard from the integration (service `create_dashboard`), overview and statistics view.

## 0.7.0

- Weekly profile, month overview and interventions per day as attributes.

## 0.6.0

- Heat pumps: device types *Throttle power* and *Change settings*, comfort guard, minimum duration, pause after
  taking back. Compatibility lists.

## 0.5.0

- Device type *Battery* (release by settings and values, minimum state of charge, restore).

## 0.4.x

- Load forecast (typical import per weekday and quarter hour, risk windows).

## 0.3.0

- Cost and savings (prices configurable), "use peak already reached", message on intervention; every feature switchable,
  default on.

## 0.2.0

- Devices as config subentries (add, reconfigure, delete on the integration page); migration from 0.1.

## 0.1

- Decision logic (quarter-hour budget), Home Assistant integration with set-up dialog, observe mode, tests.
