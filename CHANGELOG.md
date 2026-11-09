# Changelog / Änderungen

Format: newest first. German version below each English block is a short summary in German.

## Unreleased

- **evcc loadpoint** (new device type, experimental): a wallbox that evcc controls. The guard sets the loadpoint's maximum current
  (a ceiling, evcc keeps regulating below it), works with the current evcc offers right now and gives back the original ceiling,
  also after a restart. Charging is never stopped, evcc's mode is not touched. Only the address of evcc is needed (password if evcc
  asks for one); the connection and the loadpoint are checked when saving. Tested against a demo evcc 0.319.0, not on hardware.
  *Deutsch:* neuer Gerätetyp evcc-Ladepunkt (experimentell): der Wächter setzt die Obergrenze des Ladestroms in evcc und gibt die
  ursprüngliche zurück.
- **Grid import from evcc** (optional, general settings): the entered sensor always wins; evcc is used without a sensor, or as a
  reserve (switch, default on) while the sensor has no usable value. Never averaged; a clear difference (over 0.3 kW and 15 % for
  two minutes) is noted once in the log. Attributes `grid_source`, `grid_evcc_kw`, `sources_differ` on the status sensor.
  The grid import sensor is now optional when evcc is entered. *Deutsch:* Netzbezug aus evcc, der eigene Sensor gilt zuerst,
  evcc als Reserve, nie gemittelt, Abweichungen werden gemeldet.
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
