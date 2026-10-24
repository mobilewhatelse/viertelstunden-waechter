"""Constants of the quarter-hour peak guard."""

from datetime import timedelta

DOMAIN = "viertelstunden_waechter"
PLATFORMS = ["number", "select", "sensor"]
UPDATE_INTERVAL = timedelta(seconds=20)

# general settings (entry.data / entry.options)
CONF_GRID_POWER = "grid_power"          # sensor, grid import power (W or kW); negative values (export) count as 0
CONF_GRID_ENERGY = "grid_energy"        # sensor, grid import counter (Wh/kWh/MWh), optional but recommended
CONF_LIMIT = "limit_kw"
CONF_MARGIN = "margin_kw"
CONF_CONDITION = "condition_entity"     # optional: guard only works while this is on
CONF_LOCK = "lock_entity"               # optional: "active" is refused while this is on (e.g. an older guard)
CONF_NOTIFY = "notify_services"         # optional: comma-separated notify services
CONF_STARTUP_MODE = "startup_mode"
CONF_DEVICES = "devices"

# device settings
D_ID = "id"
D_KIND = "kind"
D_NAME = "name"
D_PRIORITY = "priority"
D_POWER = "power_entity"
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
D_OFF_SCRIPT = "off_script"

MODE_OFF = "off"
MODE_OBSERVE = "observe"
MODE_ACTIVE = "active"
MODES = [MODE_OFF, MODE_OBSERVE, MODE_ACTIVE]
STARTUP_RESTORE = "restore"
STARTUP_MODES = [STARTUP_RESTORE, MODE_OBSERVE, MODE_ACTIVE, MODE_OFF]

STATUS_OPTIONS = ["off", "locked", "idle", "no_data", "observing", "would_intervene", "ready", "intervening"]
