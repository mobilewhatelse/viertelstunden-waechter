"""Constants of the quarter-hour peak guard."""

from datetime import timedelta

DOMAIN = "viertelstunden_waechter"
PLATFORMS = ["number", "select", "sensor", "switch"]
UPDATE_INTERVAL = timedelta(seconds=20)

# general settings (entry.data / entry.options)
CONF_GRID_POWER = "grid_power"          # sensor, grid import power (W or kW); negative values (export) count as 0
CONF_GRID_INVERT = "grid_invert"        # the grid sensor counts import as negative: turn the sign round
CONF_EVCC_URL = "evcc_site_url"          # optional: evcc as source of the grid import (own sensor wins)
CONF_EVCC_PASSWORD = "evcc_site_password"
CONF_EVCC_BACKUP = "evcc_backup"        # evcc takes over while the grid sensor has no usable value (default on)
CONF_GRID_ENERGY = "grid_energy"        # sensor, grid import counter (Wh/kWh/MWh), optional but recommended
CONF_LIMIT = "limit_kw"
CONF_MARGIN = "margin_kw"
CONF_CONDITION = "condition_entity"     # optional: guard only works while this is on
CONF_LOCK = "lock_entity"               # optional: "active" is refused while this is on (e.g. an older guard)
CONF_NOTIFY = "notify_services"         # optional: comma-separated notify services
CONF_STARTUP_MODE = "startup_mode"
CONF_MAX_AGE = "max_reading_age_s"      # a grid reading older than this counts as missing (0 = never)
DEFAULT_MAX_AGE_S = 120
CONF_VOLTAGE = "mains_voltage"          # voltage of one phase, default 230 V
CONF_AI_TASK = "ai_task_entity"         # optional: AI task entity for the explainer
CONF_WEATHER = "weather_entity"         # optional: weather entity (forecast of the outdoor temperature)
CONF_OUTDOOR_TEMP = "outdoor_temp_entity"  # optional: outdoor temperature sensor (more exact for learning, history)
CONF_PLANNER = "planner_entry"                # optional: the car planner (a config entry), its charge plan sensors are found automatically
CONF_CHARGE_PLAN = "charge_plan_entities"  # optional: charge plan sensors of a car planner (attributes windows, departure)
CONF_DEVICES = "devices"

# device settings
D_ID = "id"
D_EVCC_URL = "evcc_url"                # evcc: address, e.g. http://192.168.1.20:7070
D_EVCC_LOADPOINT = "evcc_loadpoint"    # evcc: number of the loadpoint (1 = first)
D_EVCC_PASSWORD = "evcc_password"      # evcc: password, only if evcc asks for one
D_EVCC_ONE_PHASE = "evcc_one_phase"    # evcc: the guard may switch the loadpoint to 1 phase (if the charger can)
D_KIND = "kind"
D_NAME = "name"
D_PRIORITY = "priority"
D_POWER = "power_entity"
D_POWER_INVERT = "power_invert"        # the power sensor of the device counts consumption as negative
D_SWITCH = "switch_entity"
D_CURRENT = "current_entity"
D_PHASE = "phase_entity"
D_PHASES = "phases_entity"
D_ONE_PHASE = "one_phase_option"
D_MIN_CURRENT = "min_current"
D_MAX_CURRENT = "max_current"
D_MIN_POWER = "min_power_w"
D_POWER_W = "power_w"
D_MAX_OFF = "max_off_min"
D_ALLOW = "allow_entity"                # optional: intervention only while this is on
D_RESTORE = "restore_entity"            # optional (switch): switched back on only while this is on
D_ON_SCRIPT = "on_script"
D_SOC = "soc_entity"                    # battery: state of charge sensor
D_MIN_SOC = "min_soc"                   # battery: released only at or above this state of charge (%)
D_REL1 = "release_entity_1"             # battery: setting that releases the battery ...
D_REL1_VALUE = "release_value_1"        # ... and the value that does it
D_REL2 = "release_entity_2"
D_REL2_VALUE = "release_value_2"
D_RESTORE_ORIG = "restore_original"     # battery/setting: put the original values back (default on)
D_VALUE = "value_entity"                # throttle: the number that is lowered (percent, watts, amps ...)
D_MIN_VALUE = "min_value"               # throttle: never lower than this
D_MAX_VALUE = "max_value"               # throttle: normal value
D_STEP = "step"                         # throttle: step size
D_COMFORT = "comfort_entity"            # setting/throttle: sensor that must not fall below the minimum (room, hot water)
D_COMFORT_MIN = "comfort_min"
D_OBSERVE = "observe_only"                # the guard only writes what it would do with this device
D_HOLD = "hold_min"                     # minimum time an intervention is kept
D_PAUSE = "pause_min"
D_TARGET_SOC = "target_soc"             # vehicle: target state of charge (%)
D_TARGET_ENTITY = "target_soc_entity"   # vehicle: optional sensor/number that overrides the target
D_CAPACITY = "capacity_kwh"             # vehicle: battery capacity
D_DEPARTURE = "departure_entity"        # vehicle: time / datetime of the next departure
D_CONNECTED = "connected_entity"        # vehicle: optional, on = car is plugged in
D_CHARGE_MAX = "charge_kw_max"          # vehicle: what the wallbox can deliver
D_CHARGE_MIN = "charge_kw_min"          # vehicle: lowest charging power (1 phase, 6 A = 1.4 kW)
D_EFFICIENCY = "charge_efficiency"     # vehicle: share of the wallbox energy that reaches the battery (%)
D_BASE = "house_base_kw"                # vehicle: house base load that the solar surplus must cover first
D_START = "start_entity"                # vehicle: command that allows charging ...
D_START_VALUE = "start_value"
D_STOP = "stop_entity"                  # ... and the one that pauses it
D_STOP_VALUE = "stop_value"                   # minimum pause after taking back (compressor protection)
D_OFF_SCRIPT = "off_script"
D_RESERVE_ENTITY = "reserve_entity"     # battery: setting that keeps the charge (battery reserve before a peak) ...
D_RESERVE_VALUE = "reserve_value"       # ... and the value that does so
D_RESERVE_LEAD = "reserve_lead_min"     # battery: start holding this long before a forecast risk window

MODE_OFF = "off"
MODE_OBSERVE = "observe"
MODE_ACTIVE = "active"
MODES = [MODE_OFF, MODE_OBSERVE, MODE_ACTIVE]
STARTUP_RESTORE = "restore"
STARTUP_MODES = [STARTUP_RESTORE, MODE_OBSERVE, MODE_ACTIVE, MODE_OFF]

STATUS_OPTIONS = ["off", "locked", "idle", "no_data", "observing", "would_intervene", "ready", "intervening"]
