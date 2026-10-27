# Changelog / Änderungen

Format: newest first. German version below each English block is a short summary in German.

## Unreleased

- (nothing yet)

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
- **English log lines and messages:** the guard's own texts follow the Home Assistant language (German or English).

*Deutsch:* Haus und Auto in der Prognose getrennt (volles oder nicht angestecktes Auto zählt nicht), Akku-Reserve vor einer
Spitze (Standard aus), CSV-Export, KI-Erklärer (Standard aus); Protokoll und Meldungen auch auf Englisch.

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
