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

## Installation

HACS → ⋮ → Custom repositories → this repository, category *Integration* → install → restart Home Assistant →
Settings → Devices & services → Add integration → *Viertelstunden-Wächter*.

Then **Configure**:

| Device type | What the guard does | Needs |
|---|---|---|
| Wallbox | lowers the current (3-phase down to the minimum, then optionally 1-phase) | charging power sensor, current setting (`number`), optional phase selection (`select`) |
| Switchable device | switches off / on again | switch, optional power sensor |
| Emergency action | runs a script, a second script undoes it | scripts (e.g. "release home battery") |

Each device has a **priority** (1 = restricted first, 10 = only if nothing else helps), an optional
*intervention only while* entity, and for switches/scripts a maximum off time.

## Entities

| Entity | Meaning |
|---|---|
| `select` Mode | Off / Observe only / Active |
| `select` Strategy | Least loss of comfort / Strict priority order |
| `number` Limit, Safety margin | kW |
| `sensor` Status | with attributes `interventions`, `recent`, `today` (log lines with reasons) |
| `sensor` Quarter-hour energy so far, forecast, allowed import now | running quarter hour |
| `sensor` Last quarter hour | kW, with long-term statistics |
| `sensor` Peak this month | kW |
| `sensor` Interventions today | count, attribute `observed` for observe mode |

## Development

```
python -m unittest discover tests      # engine tests and house simulation, no Home Assistant needed
python tests/sim.py                    # one simulated evening: car + cooker + pool + water heater
```

`engine.py` contains all decisions and has no Home Assistant imports.

## Licence

MIT
