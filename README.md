# Viertelstunden-Wächter (Quarter-Hour Peak Guard)

Home Assistant integration that keeps the **average grid import of every quarter hour** below a limit, by
throttling the wallbox and switching flexible loads only as far as needed.

> Status: **0.1, early test version.** Runs in observe mode first. Use at your own risk.

## What is this for?

- **Purpose:** Power-based grid tariffs (in Austria from 2027, elsewhere already) bill the highest
  quarter-hour average of the month. One evening with the car charging at 11 kW while the oven is on can set
  the price for the whole month.
- **For whom:** Home Assistant users with a wallbox and/or switchable loads (pool pump, water heater, heat pump
  boost, home battery) and a grid meter in Home Assistant.
- **What you get:** a guard that works with an **energy budget per quarter hour** instead of a hard power cap:
  short peaks pass, the car keeps charging (never stopped, only throttled, if allowed down to 1 phase), other
  devices are paused by priority and given back stepwise. Every decision is logged with its reason.
- **What it is not:** no replacement for the fuses and the load management required by electrical codes, no
  tariff calculator, no cloud service. It needs no internet and no AI.

## How it decides

Every 20 seconds:

```
E        energy imported so far in this quarter hour (meter counter, cross-checked)
allowed  = (target × 0.25 h − E) / remaining time
excess   = average import of the last minute − allowed
```

`target = limit − safety margin`. If there is an excess, the guard picks devices:

- **Least loss of comfort** (default): the cheapest set of devices (sum of priorities) that is enough.
  0.8 kW too much → the pool pump alone, if it is less important than the car.
- **Strict priority order:** like a fixed list, priority 1 first.

Giving back happens in reverse: the most important device first, only with headroom that held for two minutes
(cookers cycle), at most one step per minute, the wallbox stepwise. A switched-off device stays off at least
5 minutes and never longer than its *maximum off time*.

Safety:

- **Observe mode:** decides and logs, but switches nothing. Start with it.
- Readings missing for 90 s, guard switched off, condition off, Home Assistant restart or integration
  unloaded → everything the guard changed is given back.
- Only what the guard changed itself is restored; a device switched on again only if it is still off and its
  optional "switch on again only while" entity is on.
- A *lock entity* refuses active mode, e.g. while another guard still runs.
- Implausible counter jumps (after an outage) are ignored.

> **Deutsche Anleitung:** [docs/ANLEITUNG.md](docs/ANLEITUNG.md) – Einrichtung, Messung, Beispiele, Umstellen.

## Grid measurement: what the guard needs

Two sensors, from any integration (no HACS needed for them):

| Sensor | Unit | Required | Note |
|---|---|---|---|
| Grid import power | W or kW | yes | updated every few seconds; a net sensor (negative = export) also works, negative counts as 0 |
| Grid import energy counter | Wh, kWh or MWh | recommended | makes the quarter-hour energy exact after restarts |

Typical sources, all with integrations built into Home Assistant:

1. **The inverter's own meter** at the grid connection point (Fronius, SMA, Huawei, SolarEdge, …).
2. **The utility smart meter's customer interface** (in Austria: optical/M-Bus interface, key from the grid
   operator) with a reader via **ESPHome** or **MQTT**. About one value per second – the best source.
3. **A meter in the distribution board**, e.g. a 3-phase energy meter via its integration or **Modbus**.

**Not suitable:** the grid operator's web portal. Its 15-minute values arrive the next day – fine for
statistics, far too late for control.

## Installation

HACS → ⋮ → Custom repositories → this repository, category *Integration* → install → restart Home Assistant →
Settings → Devices & services → Add integration → *Viertelstunden-Wächter*.

Then add the devices **on the integration page**: the buttons *Add wallbox / switchable device / emergency
action* create one entry per device; each entry has ⋮ → *Reconfigure* / *Delete*. The gear icon opens the
general settings. (Devices are config subentries; version 0.1 stored them in the options and migrates
automatically.)

The device types:

| Device type | What the guard does | Needs |
|---|---|---|
| Wallbox | lowers the current (3-phase down to the minimum, then optionally 1-phase) | charging power sensor, current setting (`number`), optional phase selection (`select`) |
| Switchable device | switches off / on again | switch, optional power sensor |
| Battery | releases the home battery so it feeds the house (settings and values you enter, previous values are put back) | state of charge sensor, one or two settings (`number` / `select` / switch) |
| Emergency action | runs a script, a second script undoes it | scripts, for anything the other types cannot do |

Each device has a **priority** (1 = restricted first, 10 = only if nothing else helps), an optional
*intervention only while* entity, and for switches/scripts a maximum off time.

The guard knows no brands, only roles. Any wallbox whose integration offers a settable charging current works
(phase switching optional); a home battery is controlled through two small scripts, because every battery is
controlled differently. Wallboxes that can only be started and stopped are not supported (the car is never
stopped).

### Battery

The device type **Battery** releases the home battery in an emergency, without scripts or helper templates:

| Field | Meaning |
|---|---|
| State of charge, minimum state of charge | released only at or above the minimum, given back if it falls below |
| Setting that releases the battery + value | e.g. a `number` "maximum output power" with value `800`, or a `select` "mode" with the option `on`; a second setting is optional |
| Expected relief (W) | how much the release lowers the import (planning, savings estimate) |
| Maximum duration | taken back after this time in any case (0 = no limit) |
| Put the previous values back | on: settings are restored to their values from before the release - **only those that still hold the release value**, so a value set meanwhile by another automation is left alone |
| Script after taking back | optional, e.g. to let your own automation set the battery (use it instead of restoring if your battery has its own control logic) |

The battery is offered as a measure only if at least one of its settings differs from the release value (it is
not "released" twice) and the state of charge allows it. It defaults to priority 10: last. Example:
`number.battery_max_output_power` → `800` and `select.battery_mode` → `on`.

### Which actuators work

The guard can switch something **on/off**, **lower a current** (wallbox) or **run a script**. Whatever can be
reduced to one of these works.

| Actuator | Supported | How |
|---|---|---|
| Sockets, relays, pumps, boilers | yes | switchable device (`switch`, `input_boolean`, `light`, `fan`) |
| Wallbox with a settable charging current | yes | wallbox (current `number`, optional phase `select`) |
| Heat pump / heating element with a contact (e.g. SG-Ready), air conditioner with a switch | yes | switchable device |
| Home battery, inverter modes | yes | battery (settings and values), or an emergency action (two scripts) |
| Anything that is an action in Home Assistant (scene, automation, mode select) | yes | emergency action (script) |
| `climate` entities (setpoint) | via script only | one script lowers the setpoint, one restores it |
| Devices with an adjustable **power** (stepless heating element, battery charge power) | roughly | via scripts only on/off, not stepwise |
| Wallbox that can only be started and stopped | possible, not recommended | as a switchable device it would stop charging |
| Blinds, lights, locks | no | save no relevant power |

Requirements: the device needs a **state** in Home Assistant (on/off) so the guard knows whether it runs; a
power sensor is optional (otherwise the *assumed power* is used). The guard only touches what you configured.

### What is part of the integration, and what you provide yourself

**Inside the integration** (nothing else to install): the decision engine, the device list with priorities and
strategies, observe mode and the lock, the safety rules, the entities (mode, strategy, limit, margin, price
numbers, the four feature switches, all sensors), cost and savings, "use peak already reached", the message on
intervention, the load forecast, diagnostics.

**Outside, in your own Home Assistant** (it depends on your home, so the integration cannot ship it):

| What | Why | Typical way |
|---|---|---|
| Grid import power sensor and optional import counter | measured by your inverter or meter | the integration of your inverter, ESPHome, Modbus … |
| The entities of your devices (wallbox current, switches, power sensors) | they belong to your hardware | the integrations of the devices |
| **Optional condition entities**: *only needed while*, *lock entity*, *intervene only while*, *switch on again only while* | rules of your household | any on/off entity: a template helper, an `input_boolean`, a schedule. Example: "switch the kitchen plug on again only while its own schedule wants it on" is a template helper that reads that schedule |
| Scripts for an emergency action | only for what the other device types cannot do | two small scripts (intervene / undo); a home battery needs none: use the device type *Battery* |
| A dashboard | your taste | the entities above; the German guide has a card for the configuration |

So the helper entities in an installation like the author's ("kitchen may switch on again", "battery emergency
possible") are **not** part of the integration: they are conditions and scripts you create for your own devices.
The integration only asks for them where you enter a device.

### Wallbox compatibility

What the guard needs from a wallbox integration: a **charging power sensor** and a **settable charging current**
(`number`, A). Checked in the integrations' source code on 2026-10-25; only the Wattpilot was tried on real
hardware. Entity names change between versions - look for them in your own installation.

| Integration | Charging current as `number` | Power sensor | Usable |
|---|---|---|---|
| Wattpilot (HACS, `wattpilot-HA`) | yes, "Max Charging Current" | yes | **yes** (tested; phase selection available) |
| Wallbox (Home Assistant core) | yes, "Maximum charging current" | yes (kW) | **yes** (no phase switching) |
| OpenEVSE (core) | yes, "Charge rate" (A) | yes | **yes** |
| Zaptec (HACS) | yes, "charger_max_current" | yes (W) | **yes** |
| OCPP (HACS, `lbbrhzn/ocpp`) | yes, "Maximum Current" | yes | **yes** (sets a charging profile; check how your charger reacts) |
| Alfen (HACS) | yes, several "max current" numbers | yes | **with care** - these are device settings; frequent writing was not checked |
| KEBA (core) | no, only the service `keba.set_current` | yes | **via helper** (below) |
| Easee (HACS) | no, only services (e.g. dynamic limit) | yes | **via helper** (below) |
| Ohme (core) | no (numbers are target percentage etc.) | yes | no |
| Blue Current (core) | no (only start/stop switch) | yes | no |
| myenergi (HACS) | no (minimum green level, priorities) | yes | no |
| evcc (HACS) | no current number found | yes | no - regulate in evcc itself |
| go-e, openWB, Tesla Wall Connector, others | not checked | | unknown |

**Via helper** (charger sets the current only through a service): create an `input_number` helper (A, step 1,
your min/max) and an automation that calls the service with the helper's value when it changes. Enter the helper
as "charging current setting". The guard then changes the helper and the automation passes it on.

### Roadmap

- **Power throttle** device type: lowers a `number` (heating element power, battery charge power) stepwise
  between a minimum and a maximum, like the wallbox current, and gives it back stepwise. Not built yet – it is
  added when someone needs it and can test it on real hardware.
- Charge plan for the car, battery reserve before an expected peak, early and gentler intervention based on the
  forecast, and a daily plan proposed by an AI task (validated against hard limits).

### Cost, savings and optional features

Three switches, **all on by default** (the last state is restored after a restart):

| Switch | What it does |
|---|---|
| **Use peak already reached** | The tariff bills the highest quarter hour of the month. If a peak above the limit has already happened this month (say 12 kW), quarter hours below it cost nothing extra – the guard then works with that peak as its limit for the rest of the month (the limit number itself stays unchanged). Only helps after a peak above the limit; with a month peak below the limit nothing changes. The month peak counts from the moment the integration measures it. |
| **Message on intervention** | A message (via the notify services of the general settings) at the first real intervention, at most every 30 minutes. Not sent in observe mode. |
| **Calculate cost and savings** | Shows what the month's peak costs and what it would have cost without the guard. |

**Entering the costs:** the numbers *Demand charge up to the threshold* and *Demand charge above the threshold*
(EUR per kW and year) and *Price threshold* (kW, default 10) – from the tariff sheet of your grid operator. They
default to 0 (nothing is shown until you enter them). The monthly peak is billed with one twelfth of the annual
price; the part of the peak up to the threshold with the first price, the part above with the second:

```
cost = ( min(peak, threshold) × price_low + max(peak − threshold, 0) × price_high ) / 12
```

Sensors: *Demand charge this month*, *… without the guard (estimate)*, *Savings this month (estimate)*,
*Savings this year (estimate)* (attribute `months`), *Relief now (estimate)*.

**How the savings are estimated** (only in active mode, nothing is "saved" while only observing): for every quarter
hour the guard adds up what its interventions kept out of the grid import – wallbox: what its setting would have
allowed at the original current minus what it can draw now (never less than it really draws); switchable device:
the power it had when it was switched off, while it is off; emergency action: the configured expected reduction.
The highest of these "unguarded" quarter hours of the month is billed with the tariff. This is an estimate, not a
measurement.

### Load forecast

Switch **Learn and show the load forecast** (default on). The guard learns the typical grid import for every
weekday and quarter hour of the day: each finished quarter hour adds a sample to its slot (what the import would
have been without the guard), a slot keeps the latest 8 samples. Per slot: *typical* = median, *high* = second
highest sample (the highest if fewer than four samples). A quarter hour is a **risk** if its *high* exceeds the
current target and at least two samples exist.

On the first start the model is filled from the **hourly statistics of the import counter** (up to 12 weeks, so
the forecast is useful right away). An hourly mean is a lower bound for its four quarter hours, so peaks are
underestimated at first and become accurate with the live samples. Needs the counter in the general settings and
the recorder.

Sensors:

- *Typical import now (forecast)* – attributes `high_kw`, `samples_here`, `samples_total`, `learned_slots`
- *Expected peak in 24 h (forecast)* – attributes `windows` (risk windows with start, end, `high_kw`) and `hours`
  (hourly `typical` / `high`, for charts and cards)
- *Next peak risk* – timestamp of the next or running risk window (attributes `until`, `high_kw`)

The forecast is displayed only for now; it does not change what the guard does. It is the basis for the planned
charge plan, battery reserve and early intervention.

### Seeing what is configured

- The **integration page** lists all devices; the gear icon holds the general settings.
- The status sensor carries the attribute `configuration` (for a dashboard card, example in the German guide).
- ⋮ → **Download diagnostics**: configuration, current values, interventions and the recent log.

### From observe to active

1. Run a few evenings in **Observe only** and read the status attribute `today` (lines marked "observed").
2. If an older guard or automation still controls the same devices, set it as *lock entity*: active mode is
   refused while it is on.
3. Switch the old one off, set **Active**, watch one evening with the car charging and the cooker on.
4. Back: set **Observe only** – everything the guard changed is given back immediately.

## Entities

| Entity | Meaning |
|---|---|
| `select` Mode | Off / Observe only / Active |
| `select` Strategy | Least loss of comfort / Strict priority order |
| `number` Limit, Safety margin | kW |
| `sensor` Status | with attributes `interventions`, `recent`, `today` (log lines with reasons), `configuration` |
| `sensor` Quarter-hour energy so far, forecast, allowed import now | running quarter hour |
| `sensor` Last quarter hour | kW, with long-term statistics |
| `sensor` Peak today | kW, attribute `days`: peak per day of the last 31 days with time |
| `sensor` Peak this month | kW |
| `sensor` Interventions today | count, attribute `observed` for observe mode |
| `number` Demand charge up to / above the threshold, Price threshold | EUR/kW/year and kW |
| `switch` Use peak already reached, Message on intervention, Calculate cost and savings | default on |
| `sensor` Demand charge this month, … without the guard, Savings this month / this year, Relief now | EUR and kW, estimates |
| `switch` Learn and show the load forecast | default on |
| `sensor` Typical import now, Expected peak in 24 h, Next peak risk | forecast, attributes `windows`, `hours` |

## Development

```
python -m unittest discover tests      # engine tests and house simulation, no Home Assistant needed
python tests/sim.py                    # one simulated evening: car + cooker + pool + water heater
```

`engine.py` contains all decisions and has no Home Assistant imports.

## Licence

Dual-licensed: **AGPL-3.0** for free use (see [LICENSE](LICENSE)), or a **commercial licence** for use in
products and services without the AGPL obligations. Details in [LICENSING.md](LICENSING.md).
