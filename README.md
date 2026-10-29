# Viertelstunden-Wächter (Quarter-Hour Peak Guard)

Home Assistant integration that keeps the **average grid import of every quarter hour** below a limit, by
throttling the wallbox and switching flexible loads only as far as needed.

> Status: **0.13, in daily use on one installation** (see `docs/COMPATIBILITY.md` for what was tried on real hardware).
> Start in observe mode. Use at your own risk.

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
- **Confirmation:** every real intervention is checked in the readings (see *Confirmation of commands*).

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
| Change settings | changes one or two settings (block contact, operating mode ...) and puts them back | the settings (`switch`, `select`, `number`) and the value for "lowered" |
| Throttle power | lowers a `number` (percent, watts, amps) stepwise between a minimum and its normal value and gives it back stepwise | a number entity, optional power sensor |
| Emergency action | runs a script, a second script undoes it | scripts, for anything the other types cannot do |
| Vehicle (charge plan) | plans when the car should charge; optionally pauses/allows charging accordingly | state of charge sensor, departure time, see *Charge plan* |

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

### Heat pumps and other devices with a power limit

Heat pumps are controlled in three ways in Home Assistant; the guard supports all three. **Tested in the
simulator only** (no heat pump was available) - try it in observe mode first.

| Your heat pump offers | Device type | Example |
|---|---|---|
| a **power limit** as a number (percent, watts, kilowatts; often via Modbus) | **Throttle power** | number `maximum compressor power` 100 → 30 in steps of 10 |
| a **block contact** (SG-Ready / utility block) as one or two switches | **Change settings** | block switch → `on` (SG-Ready mode 1: switch 1 `on`, switch 2 `off`) |
| an **operating mode** as a selection | **Change settings** | mode select → `Off` or `Eco` |
| only an on/off switch | switchable device | always with a *maximum off time* |
| a `climate` entity (setpoint) | emergency action (script) | a script lowers the setpoint, one restores it |

**Throttle power:** with a power sensor the new value is calculated from the real consumption (power follows the
value), without it the value is lowered by one step per cycle. The guard never goes below the *lowest value* and
gives the value back stepwise when there is headroom.

**Protecting the heat pump** (all optional, for *Throttle power* and *Change settings*):

- **Comfort sensor and comfort minimum:** a room or hot water temperature. While it is below the minimum the
  device is left alone, and an intervention that is running is ended.
- **Minimum duration:** an intervention is kept at least this long (default 5 minutes).
- **Pause after taking back:** wait this long before the next intervention - keeps the compressor from short
  cycles (switchable devices have this field too).
- **Maximum duration:** taken back after this time in any case.

*Change settings* restores the previous values after the intervention, but only those that still hold the changed
value (a value set meanwhile by another automation is left alone); switch off "put the previous values back" and
use the script field if your heat pump has its own control logic.

### Which actuators work

The guard can switch something **on/off**, **lower a current** (wallbox) or **run a script**. Whatever can be
reduced to one of these works.

| Actuator | Supported | How |
|---|---|---|
| Sockets, relays, pumps, boilers | yes | switchable device (`switch`, `input_boolean`, `light`, `fan`) |
| Wallbox with a settable charging current | yes | wallbox (current `number`, optional phase `select`) |
| Heat pump / heating element with a contact (e.g. SG-Ready), air conditioner with a switch | yes | switchable device |
| Home battery, inverter modes | yes | battery (settings and values), or an emergency action (two scripts) |
| Heat pump with power limit, block contact or operating mode | yes (simulator only) | throttle power / change settings, see above |
| Anything that is an action in Home Assistant (scene, automation, mode select) | yes | emergency action (script) |
| `climate` entities (setpoint) | via script only | one script lowers the setpoint, one restores it |
| Devices with an adjustable **power** (stepless heating element, heat pump percent, charge power) | yes | throttle power (stepwise) |
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

**Full list for wallboxes, batteries and heat pumps, with the test status of every integration (tested by us / entity types verified in the source / help wanted): [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).** Nothing is marked "tested" for the new device types yet - reports are welcome (see the end of that page).

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

Nothing in this list is built yet (done in 0.13: house and car apart, battery reserve, CSV export, AI explainer, English texts, the phone view *Today*).
The order is a proposal, not a promise.

**Planned**

1. **Publishing:** the installation test on a fresh Home Assistant 2026.10.3 (Docker, `tests/install`) passed on
   2026-10-25 - config flow from scratch, devices, observe and active mode, release, services, restart - and
   **hassfest passes**. Still open: the HACS validation (needs a public repository), repository topics, a first release,
   and real-world reports from other installations.
2. **Real-hardware tests** of *Throttle power* and *Change settings* (heat pumps) and of the battery release on other
   makes - until then they are simulator-tested only. Test reports are welcome (issue template *device test report*).
3. **Charge plan closer to the risk windows:** avoid forecast peaks when placing the charging quarters, and a *daily
   plan* that combines solar forecast, departure times and the learned load pattern.
4. **Connectors (optional, opt-in):** the CSV export exists (0.13); where a platform offers a documented interface, a
   connector could send the data there (for example platforms for energy
   communities). A connector depends entirely on the other platform's interface and is a separate optional part:
   nothing leaves the installation unless the user sets it up.
5. **Dynamic tariffs:** charging by day-ahead price as one more input of the plan (only useful with such a tariff).

**AI features** (the explainer is built in 0.13, the others are planned; optional, **off by default and off after a restart**, with a daily cost limit). The AI is used
through Home Assistant's *AI task* entity, so every user chooses the model (cloud or local) and no key is built in.
**The rule: the AI explains, advises and plans - what is switched now is always decided by the fixed rules** (every 20
seconds, also without internet), and every AI proposal is checked against hard limits before it is used.

| Function | What it does | Risk |
|---|---|---|
| **Explainer** (built, 0.13) | Turns the day's interventions into a short text, optionally as a message ("Pool paused 12 min so the car is full by 7") | none, read only |
| **Weekly review with suggestions** | "Three tight quarter hours, all Sundays at 18:00 with oven and car. Suggestion: start charging at 20:00." Nothing changes without confirmation | low |
| **Set-up by conversation** | A sentence like "the pool does not matter, the freezer may be off 30 min at most" becomes a proposal for devices, priorities and maximum off time that the user confirms | low |
| **Ask the guard** | "Why was the wallbox throttled yesterday evening?" via Assist, chat or the Home Assistant MCP server | none |
| **Daily plan** | From solar forecast, weather, appointments and the learned load pattern a proposal (e.g. charge the car 11-15 h, battery reserve 30 %), validated by the rules before use | medium, therefore proposal only |

Learning of load patterns (the cooker cycles, the oven on Sundays) already needs no language model: the guard does it
locally with simple statistics (see *Load forecast*).

### Cost, savings and optional features

Three switches, **all on by default** (the last state is restored after a restart):

| Switch | What it does |
|---|---|
| **Use peak already reached** | The tariff bills the highest quarter hour of the month. If a peak above the limit has already happened this month (say 12 kW), quarter hours below it cost nothing extra – the guard then works with that peak as its limit for the rest of the month (the limit number itself stays unchanged). Only helps after a peak above the limit; with a month peak below the limit nothing changes. The month peak counts from the moment the integration measures it. |
| **Message on intervention** | Via the notify services of the general settings: (1) at the first real intervention a message **with everything the guard did in that step** (e.g. "Wallbox 16 A -> 12 A (3-phasig, 1.6 kW zu viel)"), at most every 30 minutes; (2) when the guard has given everything back a **summary of all steps** with times (up to 15 lines). Not sent in observe mode. |
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

### Confirmation of commands, early warning, weekly report

**Confirmation of commands (always on, nothing to set up).** A "done" from a service call proves nothing: a cloud
wallbox may accept the command and ignore it, a smart plug may be offline. The guard therefore reads the result
back about 60 seconds after every real intervention:

| Device | What must show |
|---|---|
| Wallbox | the current entity is at or below the new value, and after the phase pause the charging power is not clearly above what the new current allows |
| Switchable device | the switch is off |
| Throttle | the number has the new value |
| Battery / setting | the release value is set (nothing left to release) |

If not, the command is **repeated once**. If it still does not show, the guard logs it, sends one message per
device (at most every 30 minutes) and leaves that device alone for 10 minutes, so the **next lever of the order
is used** instead of waiting for a device that does not react. When the device follows later, it is used again.
Releases (giving back) are not checked: if one fails, the device simply stays limited and the guard tries again.
Observe mode does not check anything (nothing is sent). The count is the attribute `unconfirmed` and appears in the
weekly report; log lines read "no reaction ... repeating the command" and "command not carried out".

**Early warning** – switch *Early warning before an intervention*, **default off**. One message per quarter hour
when the forecast of the running quarter hour reaches 90 % of the limit while the guard has not yet intervened
(an intervention sends its own message). Useful in observe mode to see how often a quarter hour comes close.
Needs *notify services* in the general settings.

**Weekly report** – switch *Weekly report*, default on. On Monday from 07:00 the guard sends a short report of the
last full week (Monday to Sunday) via the notify services: highest quarter hour with day and time, days above the
limit, interventions (real, observed, not carried out), the month's peak and – if prices are entered – the month's
cost and the estimated saving. Nothing is sent for a week without measurements (e.g. a new installation). The last
report is the sensor *Weekly report* (state = week, attribute `text`) and shown at the end of the statistics view.
Service **Send weekly report** (`viertelstunden_waechter.send_week_report`, fields `current_week`, `push`) creates it
on demand, e.g. to see how it looks:

```yaml
action: viertelstunden_waechter.send_week_report
data:
  current_week: true   # the running week so far instead of the last full week
  push: false          # only create the sensor, send no message
```

### Language

Everything follows the language of Home Assistant: German for German installations, English for every other
language. That covers the set-up dialogs, entity names, services, the dashboard, the weekly report, the AI explainer and
(since 0.13) the log lines and messages of the guard ("Wallbox 16 A -> 12 A (3-phase, 1.7 kW too much)"). Lines that
are already in the log keep the language they were written in.

### House and car apart, battery reserve, export, AI explainer (0.13)

**House and car apart (automatic).** With a wallbox entry the guard learns two patterns from the same quarter hours:
the house without the wallbox (measured import minus the wallbox power) and the wallbox alone. The forecast normally
adds them up. If a vehicle entry says the car is **full** (state of charge at its target) or **not plugged in** (the
optional *connected* entity is off), and the wallbox is idle, the forecast leaves the car out: the usual evening charging
is then no risk window, *Throttle ahead* keeps no reserve for it and *Battery reserve* does not hold the battery for it.
The charge plan uses the house alone (it adds the car itself; before 0.13 it counted the car twice). Older data (history
import, months before the update) stay totals until they are replaced by new quarter hours (8 samples per slot).

**Battery reserve before a peak** (switch, **default off**). For a battery entry you can enter a *setting that keeps the
charge* and its value (for example the maximum output power set to a low value, or a mode such as standby) and how many
minutes before a forecast risk window it starts (default 60). With the switch on, the guard sets it before the window,
so the battery is not emptied for self-consumption and can still help in an emergency; after the window it puts back
the value it found. It only touches batteries with such a setting, does nothing while it has released the battery for an
emergency, logs every step ("Akku-Reserve: ... hält die Ladung ...") and only logs in observe mode. After a restart or
when the integration is unloaded a held battery is given back first. If your own automations change the same setting
(for example while the car charges), decide which one is in charge - the guard only puts a value back while it is still
the one it set.

**CSV export** (service `viertelstunden_waechter.export_csv`). Writes the quarter-hour load profile (kept 120 days:
start, end, import kW and kWh, estimate without the guard, wallbox kW) or the daily peaks (400 days) to
`config/viertelstunden_waechter/export/` - not a public folder. Format `standard` (comma, decimal point) or `excel_de`
(semicolon, decimal comma). Small files are also returned in the service response.

```yaml
action: viertelstunden_waechter.export_csv
data:
  kind: quarters      # or days
  days: 31
  format: excel_de
```

**AI explainer** (switch, **default off and off after every restart**). Choose an *AI task* entity in the general
settings (Settings > Devices > AI tasks; you pick the model, cloud or local - the guard has no key of its own). Every
evening at 21:00 the explainer turns the day's log into 2-4 plain sentences ("The wallbox was lowered from 16 to 12 A
at 16:45 while ..."), shows them in the sensor *Explanation of the day* and the statistics view and sends them via the
notify services. On a day without interventions no AI is asked (a fixed sentence instead). At most 4 AI calls per day;
the AI only writes text - it never decides or switches anything. Service `viertelstunden_waechter.explain_today`
(field `push`) asks on demand.

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

The forecast is displayed and feeds the charge plan. It changes what the guard does only if you switch on
**Throttle ahead using the forecast** (below).

#### Throttling ahead by the forecast (switch, default off)

Normally the guard reacts when the running quarter hour heads above the target. With the switch **Throttle ahead using
the forecast** it uses the learned weekday pattern as well: in a **risk quarter hour** (the forecast `high` is above
the target, at least 3 samples) it keeps a **reserve** free: the usual spike on top of the typical value
(`high - typical`, at most 3 kW, ignored below 0.5 kW). It then acts as if the target were that much lower - but only with
the *smooth* levers:

- the **wallbox current** is lowered (never to 0, never below your minimum),
- **throttles** (for example a heat pump in percent) are lowered stepwise,
- **no device is switched off** and **no phase switch** happens because of a forecast (that pauses charging);
  those remain reserved for a real excess.

Release is the other way round: when the risk quarter hour is over the reserve is zero and the usual stepwise
give-back follows. The log lines start with "Vorausschauend (laut Prognose Spitzen bis ... kW, typisch ... kW):", so you
can see why it acted; the status attribute `forecast_reserve_kw` shows the reserve of the running quarter hour.
Needs *Learn and show the load forecast* (on) and enough samples: the history import fills the profile at first with
hourly means (peaks underestimated), the live quarter hours make it accurate within a few weeks. In **observe mode**
it only logs what it would do. Recommended: switch it on after a few days, once the weekly profile looks right.

### Charge plan for the car

Device type **Vehicle (charge plan)**. It plans in which quarter hours the car should charge so that it reaches its
target by the next departure, and shows the plan. **Carrying it out is a separate switch, off by default.**

**What you enter:** the car's state of charge (sensor, %), the target (fixed percentage, optionally from a sensor
such as the car's charge limit), the battery capacity (kWh), the next departure (a *time* entity - the next
occurrence is used - or a date-time entity / `input_datetime` / timestamp sensor), the highest and lowest charging
power of the wallbox, the house base load and charging efficiency, optionally a "car plugged in" entity, and optionally the commands to
**allow** and **pause** charging (a button, switch, selection or number).

**How it plans** (`plan.py`, tested):

1. Energy needed = (target - state of charge) x capacity / 0.9 (charging losses).
2. **Sun first:** if a solar forecast exists, quarter hours with PV surplus (forecast minus house base load, at least
   the lowest charging power) are filled first - charging from the sun costs no grid energy.
3. **Then the quietest quarter hours**: the learned expected grid import (the *high* value of the load forecast)
   decides; a quarter hour is only used as far as *expected import + what the car takes from the grid* stays below
   the peak target.
4. If the target cannot be reached by departure the state is **Target not reachable** and the missing kWh are shown.
   The plan never pretends.

**Setting up the solar forecast:** Settings > Dashboards > **Energy** > edit your solar panels > switch on
**"Forecast production"** > choose the forecast integration (e.g. *Forecast.Solar*, set up beforehand under Settings >
Devices & services) > Save. Without this step the plan does not know the sun, even if the forecast integration is
installed.

**The solar forecast is optional and comes from the Energy dashboard.** The plan uses the solar forecast that is set
up there (Settings > Dashboards > Energy > Solar panels > *forecast*; integrations that provide one include
Forecast.Solar and Solcast). **Without one the plan still works**, but only on the expected grid import, and the
sensor shows a hint (`solar_used: false`). The hourly forecast is spread over its four quarter hours.

**Carrying it out** (switch *Also carry out the charge plan*, **off by default and always off after a restart**):
outside the planned windows the *pause* command is sent, inside them the *allow* command. It needs a pause command
(without it the plan stays advice). Safety rules:

- only while the plan can reach the target (state *Planned*) and the car is plugged in (if you entered that entity);
- if the plan is not feasible, not needed, has no departure, the switch is turned off, the integration unloads or
  Home Assistant restarts, the *allow* command is sent so that the car charges normally;
- at most one command per five minutes while the plan runs; resuming is never delayed;
- the peak guard still works on top of it and, as always, never stops the car by itself.

**Limits:** only the first vehicle entry is used; the plan is advice based on habits (the load forecast) and a
forecast, not a guarantee; the car may behave differently (it can end a session by itself); it has **not been tried on
real hardware yet** - start with the switch off and compare the plan with what you would do.

Sensor *Charge plan* (states: off, no vehicle, state of charge missing, no departure time, not needed, planned,
target not reachable) with the attributes `windows`, `text`, `needed_kwh`, `planned_kwh`, `solar_kwh`, `grid_kwh`,
`shortfall_kwh`, `ready_at`, `latest_start`, `departure`, `soc`, `target_soc`, `solar_used`, `paused_by_plan`, `hint`.

### Dashboard

Service **Create dashboard** (`viertelstunden_waechter.create_dashboard`) builds a ready-made dashboard with the
entities of *your* installation (whatever the device is called, in German or English) in three views: the overview
(settings, features, devices and priorities, now, cost and savings), **Today** - a compact single-column view for the
phone - and *Statistics and forecast* (24-hour forecast as bars, weekly profile, peaks of the last days, months,
interventions per day, charge plan). Only standard cards are used.

**The view *Today* (for the phone)** shows, top to bottom: the status of the guard; one bar with the forecast of the
running quarter hour against the target (white mark = target, red dashed mark = limit; green = safely below, yellow =
close, red = above the limit); the mode (switch between *Off*, *Observe only* and *Active* on the go); peak today,
peak this month and interventions today; a chart of every finished quarter hour of today (red above the limit); the
latest lines of today's log; and the explanation of the day when the AI explainer is on. The quarter hours come from
the attribute `today_quarters` of the sensor *Last quarter hour*. To use it as the home screen of the app, open the
dashboard on the phone and pick the view *Today*; there is no extra card to install.

The *Statistics and forecast* view (nothing to install: the charts are SVG images inside standard markdown cards,
drawn from the sensors' attributes; the colours work on light and dark themes):

| Chart | What it shows | Source | Fills after |
|---|---|---|---|
| **Forecast** | One bar per hour for the next 24 h: solid = typical grid import, light = highest expected value, red = above the target, dashed red line = target | load forecast | the history import (minutes) or a few days |
| **Typical week** | Heat map weekday x hour (0-23), two panels: *typical* and *highest values*; colour from dark blue via teal, green and yellow to orange = more import (each panel scaled to its own maximum), red = above the target | load forecast | the history import or about 2 weeks |
| **Highest quarter hour per day** | Last 6 weeks, one bar per day, red above the limit, dashed line = limit | `peaks_by_day` of the sensor *Peak today* | a day per bar; earlier days via *Import history* (hourly means = lower bound) |
| **Peak per month** | One bar per month with the value, dashed outline = estimate without the guard, line = limit | month history of the sensor *Peak this month* | a month per bar, or via *Import history* |
| **Hourly graph** | Standard statistics graph of the quarter-hour peaks per hour, last 3 days | recorder statistics | a few hours |

Below the charts: tables for the highest days, the months and the interventions per day. Each chart can show
"not enough data yet" instead of bars; that is normal on a fresh installation. If images are not shown, reload the
dashboard (clear the frontend cache in the app).

- With a dashboard URL (e.g. `waechter`): create an empty dashboard first (Settings > Dashboards > Add), then call the
  service with its URL - its views are replaced.
- Without a URL: the YAML is returned and shown as a notification; paste it into a new dashboard (three dots > Edit >
  Raw configuration editor). This is the more robust way if Home Assistant changes internally.

### Importing earlier measurements

Service **Import history** (`viertelstunden_waechter.import_history`) seeds the day and month peaks from an earlier
measurement (a spreadsheet, an older script) so that statistics, the monthly cost and the "use peak already reached"
function know the past. It only raises values (a day or month that already has a higher peak keeps it); values taken
from hourly data are lower bounds.

```yaml
action: viertelstunden_waechter.import_history
data:
  days: [{date: "2026-10-01", kw: 7.8, at: "18:15"}]   # at is optional
  months: [{month: "2026-10", peak_kw: 9.1}]
```

The daily peaks of the last 400 days are available as the attribute `peaks_by_day` ({date: kW}) of the sensor *Peak
today*, for other automations and scripts. Large attributes (profile, hours, windows, days, months, ...) are excluded
from the database to keep it small.

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
| `sensor` Last quarter hour | kW, with long-term statistics, attribute `today_quarters` (finished quarter hours of today) |
| `sensor` Peak today | kW, attribute `days`: peak per day of the last 31 days with time |
| `sensor` Peak this month | kW |
| `sensor` Interventions today | count, attribute `observed` for observe mode |
| `number` Demand charge up to / above the threshold, Price threshold | EUR/kW/year and kW |
| `switch` Use peak already reached, Message on intervention, Calculate cost and savings | default on |
| `sensor` Demand charge this month, … without the guard, Savings this month / this year, Relief now | EUR and kW, estimates |
| `switch` Learn and show the load forecast | default on |
| `switch` Throttle ahead using the forecast (default off), Early warning before an intervention (default off), Weekly report (default on) | optional |
| `switch` Battery reserve before a peak (default off), AI explainer (default off, off after restart) | optional |
| `sensor` Explanation of the day | state = date, attributes `text`, `source` (ai / rule / none), `error` |
| `sensor` Weekly report | state = week, attribute `text`, `peak_kw`, `days_over`, `interventions`, `unconfirmed` |
| `sensor` Typical import now, Expected peak in 24 h, Next peak risk | forecast, attributes `windows`, `hours`, `profile` |
| `sensor` Charge plan | states and attributes see *Charge plan* |
| `switch` Calculate the charge plan (default on), Also carry out the charge plan (always off after a restart) | |

## Development

```
python -m unittest discover tests      # engine tests and house simulation, no Home Assistant needed
# tests/install: installation test with a fresh Home Assistant in Docker, see tests/install/README.md
python tests/sim.py                    # one simulated evening: car + cooker + pool + water heater
```

`engine.py` contains all decisions and has no Home Assistant imports.

## Licence

Dual-licensed: **AGPL-3.0** for free use (see [LICENSE](LICENSE)), or a **commercial licence** for use in
products and services without the AGPL obligations. Details in [LICENSING.md](LICENSING.md).
