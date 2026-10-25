# Compatibility: wallboxes, batteries, heat pumps

The guard knows no brands, only roles (see the README). Whether **your** device works depends on which entities
its Home Assistant integration offers. This page lists what we checked and what still needs help from the
community. *State of the check: 2026-10-25, integration version 0.6.0.*

## Status legend

| Symbol | Meaning |
|---|---|
| 🟡 | **In use by the authors.** Their hardware, observe mode with this integration (the release path was not yet triggered in real operation), or the same entities are used by the authors' own automations / the predecessor script. |
| 🔍 | **Entity types verified in the source code** of the integration (version in the Home Assistant release 2026.10). *Not* tested on hardware; whether your model or firmware supports the function is open. |
| ❔ | **Not checked / help wanted.** The integration has the platforms (`number`, `select`, `switch`), but the entities are generated from device definitions or were not looked at. Please test and report. |
| ❌ | **No suitable entity found** in the source check (nothing writable that lowers power or changes the mode). Use a script or an on/off switch. |

**"Tested" means:** at least one evening in the mode **Active** with a real intervention *and* the real take-back
observed, on real hardware, reported with the version number. Nobody has reached this level yet for the new
device types. Please be the first - see "How to report a test" below.

## Wallboxes (device type *Wallbox*)

Needs a charging power sensor and a settable charging current (`number`, A).

| Integration | Charging current | Status |
|---|---|---|
| Wattpilot (HACS, `wattpilot-HA`) | `number` "Max Charging Current", phase selection | 🟡 throttled live by the predecessor script; integration in observe mode |
| Wallbox (core) | `number` "Maximum charging current" | 🔍 |
| OpenEVSE (core) | `number` "Charge rate" (A) | 🔍 |
| Zaptec (HACS) | `number` "charger_max_current" | 🔍 |
| OCPP (HACS, `lbbrhzn/ocpp`) | `number` "Maximum Current" (charging profile) | 🔍 |
| Alfen (HACS) | several "max current" numbers (device settings, frequent writes not checked) | 🔍 with care |
| Tesla Fleet (core), car charging current | `number` "charge current request" (the car, not a wallbox) | 🔍 |
| KEBA (core), Easee (HACS) | only a service, no number | 🔍 via helper (`input_number` + automation) |
| Ohme, Blue Current (core), myenergi, evcc (HACS) | no current number | ❌ |
| go-e, openWB, Tesla Wall Connector, others | | ❔ |

## Home batteries and inverters (device type *Battery*, or *Change settings*)

The guard releases the battery in an emergency: it sets one or two settings to a value that lets the battery feed
the house (maximum output / discharge power, operating mode) and puts them back. Needs a state-of-charge sensor.

| Integration | Writable entities found | Idea for "released" | Status |
|---|---|---|---|
| Jackery (the authors' installation) | `select` auto standby mode, `number` maximum output power (on-grid), `sensor` battery SOC | mode `on`, power `800` | 🟡 |
| Fronius (core) | `number` battery discharge power limit (+ enable switch), charge power limit, minimum reserve, AC power limit; `switch` battery grid charging | raise the discharge limit, or lower the minimum reserve | 🔍 |
| Kostal Plenticore (core) | `number` battery min SOC, battery min home consumption, active power limitation; `select` battery charge | lower min SOC / set min home consumption | 🔍 |
| GoodWe (core) | `number` battery discharge depth, charge current, grid export limit; `select` operation mode | operation mode / discharge depth | 🔍 |
| Growatt (core, cloud) | `number` battery discharge power limit, discharge power, charge limits; `switch` AC charge | raise the discharge power (cloud delay) | 🔍 |
| Enphase Envoy (core) | `select` storage mode; `number` reserve SOC; `switch` charge from grid | storage mode / lower reserve | 🔍 |
| Powerwall via Tesla Fleet (core) | `number` backup reserve percent | lower the backup reserve (cloud delay) | 🔍 |
| SolarEdge Modbus (core) | `number` discharge limit, charge limit, backup reserve; `select` storage control / default / command mode | storage command mode / discharge limit | 🔍 |
| HomeWizard battery (core) | `select` battery group mode | the mode that discharges | 🔍 |
| Imeon (core) | `select` manager inverter mode | the discharging mode | 🔍 |
| Sigenergy local Modbus (HACS) | `number` ESS max discharging limit; `select` remote EMS control mode | raise the discharge limit | 🔍 |
| Huawei SUN2000, SolaX Modbus, EcoFlow, Zendure, Victron Modbus, AlphaESS, Anker Solix, SolarEdge Modbus Multi (HACS) | platforms exist, entities generated from device definitions | | ❔ |
| SMA, SolarEdge (cloud), Powerwall, Victron GX, Solarman, Solax, Bluetti Modbus, KACO Modbus (core) | nothing writable that lowers power found | | ❌ |

Cloud-based integrations (Growatt, Tesla, EcoFlow, ...) react with a delay of seconds to minutes; a guard working
on 15-minute averages can live with that, but test it.

## Heat pumps (device types *Throttle power*, *Change settings*, *Switchable device*)

Three kinds of control exist (see the README): a **power limit** as a number, a **block contact / SG-Ready** as
switches, an **operating mode** as a selection.

| Integration | Writable entities found | Use | Status |
|---|---|---|---|
| NIBE Modbus (core) | number / select / switch generated from the writable registers of the pump model | model dependent: power limit, mode, block | ❔ promising |
| Viessmann ViCare (core) | `select` DHW operating mode; `number` heating curve shift and slope, DHW and room temperatures; `switch` quick mode | no power limit: mode or temperature offsets (comfort trade-off) | 🔍 |
| MELCloud (core) | `select` operation mode; `number` flow temperature | operation mode | 🔍 |
| MELCloud Home (core) | `switch` standby, frost / overheat protection; `number` protection temperatures | standby switch | 🔍 |
| LG ThinQ (core) | `select` operation mode; `switch` operation power | mainly appliances / air conditioners | 🔍 |
| Midea (core) | `switch` power, auxiliary heating ...; `select` mode | mainly air conditioners | 🔍 |
| Daikin (core) | `switch` zone / toggle; climate | on/off only | ❌ for power, 🔍 for on/off |
| Modbus (core, generic) | any register you define as `number` / `switch` / `select` | if your heat pump documents a power-limit, mode or block register | 🔍 principle |
| SG-Ready via two relays (e.g. Shelly) | two `switch` entities | *Change settings*: switch 1 `on`, switch 2 `off` = mode 1 (block) | 🔍 principle |
| Ariston, Stiebel Eltron, Weheat, Wolf SmartSet, BSB-LAN, ATAG, Mitsubishi Comfort, Hisense, Fujitsu (core); Luxtronik, myVaillant, Daikin Altherma, NIBE (HACS) | not checked in detail | | ❔ |

Heat pumps need extra care: use the *comfort sensor*, *minimum duration*, *pause after taking back* and
*maximum duration* fields, and start in observe mode.

## How to report a test

Open an issue titled "Device test: <integration> <model>" with:

1. Integration (core or HACS, version) and device model / firmware
2. Device type used (wallbox / switchable device / battery / change settings / throttle power) and the entities
3. Mode used (observe or active), number of evenings, and what the guard did (the `today` lines of the status
   sensor, the diagnostics download without private data)
4. Did the take-back work? Anything surprising (delays, values that snapped back, error messages)?

Reports that reach the level "tested" are added to the table above with the integration version.
