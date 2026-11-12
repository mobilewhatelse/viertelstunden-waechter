# Viertelstunden-Wächter (Quarter-Hour Peak Guard)

A Home Assistant integration that keeps the **highest quarter hour of your grid import** below a limit. It
throttles the wallbox and pauses devices, only as long as needed.

> **Deutsch:** [docs/ANLEITUNG.md](docs/ANLEITUNG.md) · **Full manual (English):** [docs/MANUAL.md](docs/MANUAL.md)

## What is this for?

- **Purpose:** Power-based grid tariffs bill the highest quarter-hour average of the month (in Austria from 2027,
  depending on the grid operator by mid-2028 at the latest). One evening with the car charging and the oven on
  can set the price for the whole month.
- **For whom:** Home Assistant users with a wallbox or switchable loads (pool pump, water heater, heat pump,
  home battery) and a grid meter in Home Assistant.
- **What you get:** a guard that steps in only when a quarter hour would really end above your limit. The car
  keeps charging, it is throttled but never stopped. Everything is given back afterwards.
- **What it is not:** no replacement for fuses or a required load management, and no tariff calculator.

## How it works

1. **Measure.** Every 20 seconds it works out where the running quarter hour will end.
2. **Throttle.** If it gets too much, it lowers the charging current of the wallbox.
3. **Pause.** If that is not enough, it pauses devices in the order you set.
4. **Give back.** Once there is room again, everything comes back step by step.

Every decision is logged with its reason. [How it decides, in detail](docs/MANUAL.md#how-it-decides).

## What you need

- Home Assistant 2026.3 or newer.
- A **grid import power** sensor (W or kW) that updates every few seconds: the smart-meter interface, the meter
  of your inverter, or a meter in the distribution board. The web portal of the grid operator is not enough.
- Recommended: the grid import **energy counter**.

A solar plant is not needed. [More on the measurement](docs/MANUAL.md#grid-measurement-what-the-guard-needs) ·
[tested devices](docs/COMPATIBILITY.md).

## Installation

1. **Settings → Marketplace** (HACS before Home Assistant 2026.11): search for **Viertelstunden-Wächter** and
   download it.
2. Restart Home Assistant, then **Settings → Devices & services → Add integration → Viertelstunden-Wächter**.
3. Choose the grid sensors and your limit. Add your devices on the integration page.
4. Watch for a few days in **Observe only**, then switch to **Active**.

The action `create_dashboard` builds a ready-made dashboard.

## Works together with

- **[evcc](https://evcc.io):** enter the address of evcc. The guard sets only a ceiling at the loadpoint, evcc
  keeps charging. [Details](docs/MANUAL.md#evcc-loadpoint-since-014-experimental)
- **A car planner such as Plugwhen:** the guard reads its charge plan and knows when the car will charge.
  [Details](docs/MANUAL.md#the-guard-and-a-car-planner-together)

## Anonymous data (voluntary)

Off unless you switch it on. With *Share anonymous data* the guard sends a weekly usage statistic (versions,
country, kinds of devices) and, from 0.15, daily values of your devices for the device check. Never names,
entity ids, addresses or passwords. [What exactly is sent](docs/MANUAL.md#anonymous-usage-statistics-voluntary-and-feedback)

## Support

Bug reports and questions go to the [issues](https://github.com/mobilewhatelse/viertelstunden-waechter/issues).
This is a spare-time project: answers can take a few days.

## Safety and liability

The guard switches real devices. It is a free hobby project and comes **without any warranty**, as stated in
sections 15 and 16 of the AGPL-3.0. It can be wrong, switch late or not at all.

- Before **Active**, check that every device copes with being switched off and on, and that no protective
  function depends on it: frost protection, the legionella cycle of a water heater, or rules of the maker or the
  grid operator. Never connect safety-relevant loads.
- Your installation stays your responsibility. Liability that the law does not allow to be excluded (for
  example for intent or gross negligence) is not affected.

## Licence

Dual-licensed: **AGPL-3.0** for free use (see [LICENSE](LICENSE)), or a **commercial licence** for use in
products and services. Details in [LICENSING.md](LICENSING.md).
