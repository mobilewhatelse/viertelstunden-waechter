# Changelog / Änderungen

Format: newest first. German version below each English block is a short summary in German.

## 0.15.0 - unreleased

- **Device check (only with *Share anonymous data*):** once a day the guard asks our service whether the connected devices still work
  as usual. Wallbox: charging power against set current and phases (drop in power, a missing phase, a slow trend); home battery:
  usable capacity from full swings of at least 40 points; switches, pumps, water heaters: power while running ("needs more than
  usual", "draws nothing although on"); heat pump: daily energy against outdoor temperature; water heater: daily energy against its
  own mean. The guard only measures; the thresholds and the judging live on the service, so they can improve without an update.
  The request carries "days ago" instead of dates, device numbers valid only within one request, no names, entity ids or id of the
  installation; the service answers and keeps only anonymous rows of finished days. Nothing is switched, the check only tells.
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
