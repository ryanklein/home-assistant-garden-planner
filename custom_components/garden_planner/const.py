"""Constants for the Garden Planner integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "garden_planner"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATE,
    Platform.CALENDAR,
    Platform.TODO,
]

# Config entry option keys (global garden settings)
CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_UNITS = "units"
CONF_LAST_FROST = "last_frost"  # ISO date string, manual override
CONF_FIRST_FROST = "first_frost"  # ISO date string, manual override
CONF_HARDINESS_ZONE = "hardiness_zone"

# Subentry types
SUBENTRY_TYPE_BED = "bed"
SUBENTRY_TYPE_PLANTING = "planting"

# Subentry / flow field keys -- beds
CONF_NAME = "name"
CONF_SUN_EXPOSURE = "sun_exposure"
CONF_SIZE = "size"
CONF_ORIENTATION = "orientation"
CONF_SOIL = "soil"
CONF_NOTES = "notes"

# Subentry / flow field keys -- plantings
CONF_BED_ID = "bed_id"
CONF_PLANT_QUERY = "plant_query"
CONF_PLANT_SOURCE_ID = "plant_source_id"
CONF_METHOD = "method"
CONF_QUANTITY = "quantity"
CONF_SEASON_YEAR = "season_year"
CONF_SOW_DATE = "sow_date"
CONF_TRANSPLANT_DATE = "transplant_date"
CONF_HARVEST_DATE = "harvest_date"

# Providers
PROVIDER_BUNDLED = "bundled"
PROVIDER_PERENUAL = "perenual"
PROVIDER_OPENFARM = "openfarm"
DEFAULT_PROVIDER = PROVIDER_BUNDLED
PROVIDERS = [PROVIDER_BUNDLED, PROVIDER_PERENUAL, PROVIDER_OPENFARM]

# Units
UNITS_METRIC = "metric"
UNITS_IMPERIAL = "imperial"
DEFAULT_UNITS = UNITS_METRIC

# Sun exposure values
SUN_FULL = "full"
SUN_PARTIAL = "partial"
SUN_SHADE = "shade"
SUN_VALUES = [SUN_FULL, SUN_PARTIAL, SUN_SHADE]

# Water levels
WATER_LOW = "low"
WATER_MEDIUM = "medium"
WATER_HIGH = "high"
WATER_VALUES = [WATER_LOW, WATER_MEDIUM, WATER_HIGH]

# Sow methods
METHOD_DIRECT = "direct"
METHOD_TRANSPLANT = "transplant"
METHOD_BOTH = "both"
METHOD_VALUES = [METHOD_DIRECT, METHOD_TRANSPLANT, METHOD_BOTH]

# Action / task kinds
ACTION_SOW = "sow"
ACTION_TRANSPLANT = "transplant"
ACTION_WATER = "water"
ACTION_FERTILIZE = "fertilize"
ACTION_HARVEST = "harvest"
ACTION_KINDS = [
    ACTION_SOW,
    ACTION_TRANSPLANT,
    ACTION_WATER,
    ACTION_FERTILIZE,
    ACTION_HARVEST,
]

# Watering cadence (days) derived from water level
WATER_CADENCE_DAYS = {
    WATER_LOW: 7,
    WATER_MEDIUM: 3,
    WATER_HIGH: 1,
}

# Services
SERVICE_LOG_ACTION = "log_action"
SERVICE_SET_FROST_DATES = "set_frost_dates"
SERVICE_REFRESH_PLANT_DATA = "refresh_plant_data"

# Events
EVENT_TASK_DUE = f"{DOMAIN}_task_due"
EVENT_STAGE_CHANGE = f"{DOMAIN}_stage_change"

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

# Coordinator refresh cadence
UPDATE_INTERVAL_HOURS = 6
