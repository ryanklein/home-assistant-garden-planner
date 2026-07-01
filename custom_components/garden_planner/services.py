"""Services for Garden Planner.

* ``log_action`` -- record that you sowed/transplanted/watered/etc. a planting
  (buttons on each planting device call the same underlying code path).
* ``set_frost_dates`` -- override the estimated frost dates.
* ``refresh_plant_data`` -- re-fetch cached plant profiles from the provider.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ACTION_KINDS,
    CONF_FIRST_FROST,
    CONF_LAST_FROST,
    CONF_PROVIDER,
    CONF_API_KEY,
    DEFAULT_PROVIDER,
    DOMAIN,
    SERVICE_LOG_ACTION,
    SERVICE_REFRESH_PLANT_DATA,
    SERVICE_SET_FROST_DATES,
    SUBENTRY_TYPE_PLANTING,
)
from .providers import PlantProviderError, async_get_provider

if TYPE_CHECKING:
    from . import GardenConfigEntry

LOG_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): vol.In(ACTION_KINDS),
        vol.Optional("date"): cv.date,
        vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("planting_id"): cv.string,
    }
)

SET_FROST_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_LAST_FROST): cv.date,
        vol.Optional(CONF_FIRST_FROST): cv.date,
    }
)


def _garden_entry(hass: HomeAssistant) -> GardenConfigEntry:
    """Return the loaded garden config entry, or raise a user-facing error."""
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state.recoverable and getattr(e, "runtime_data", None) is not None
    ]
    if not entries:
        raise ServiceValidationError("Garden Planner is not set up")
    return entries[0]


def _planting_ids_from_call(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Resolve targeted planting ids from device targets or an explicit id."""
    ids: list[str] = []
    if planting_id := call.data.get("planting_id"):
        ids.append(planting_id)

    device_reg = dr.async_get(hass)
    for device_id in call.data.get("device_id", []):
        device = device_reg.async_get(device_id)
        if device is None:
            continue
        for domain, identifier in device.identifiers:
            if domain == DOMAIN:
                ids.append(identifier)
    return ids


async def _handle_log_action(call: ServiceCall) -> None:
    hass = call.hass
    entry = _garden_entry(hass)
    planting_ids = _planting_ids_from_call(hass, call)
    if not planting_ids:
        raise ServiceValidationError("No planting targeted for log_action")

    on = call.data.get("date") or date.today()
    known = set(entry.subentries)
    for planting_id in planting_ids:
        if planting_id not in known:
            raise ServiceValidationError(f"Unknown planting: {planting_id}")
        await entry.runtime_data.store.async_add_action(
            planting_id, call.data["kind"], on
        )
    await entry.runtime_data.coordinator.async_request_refresh()


async def _handle_set_frost_dates(call: ServiceCall) -> None:
    hass = call.hass
    entry = _garden_entry(hass)
    options = dict(entry.options)
    if (last := call.data.get(CONF_LAST_FROST)) is not None:
        options[CONF_LAST_FROST] = last.isoformat()
    if (first := call.data.get(CONF_FIRST_FROST)) is not None:
        options[CONF_FIRST_FROST] = first.isoformat()
    hass.config_entries.async_update_entry(entry, options=options)


async def _handle_refresh_plant_data(call: ServiceCall) -> None:
    hass = call.hass
    entry = _garden_entry(hass)
    options = entry.options
    provider = await async_get_provider(
        hass,
        options.get(CONF_PROVIDER, DEFAULT_PROVIDER),
        options.get(CONF_API_KEY),
    )
    store = entry.runtime_data.store
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_PLANTING:
            continue
        source_id = subentry.data.get("profile", {}).get("source_id")
        if not source_id:
            continue
        try:
            profile = await provider.async_get(source_id)
        except PlantProviderError:
            continue
        if profile is not None:
            await store.async_cache_profile(profile)
    await entry.runtime_data.coordinator.async_request_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register services once for the integration."""
    if hass.services.has_service(DOMAIN, SERVICE_LOG_ACTION):
        return
    hass.services.async_register(
        DOMAIN, SERVICE_LOG_ACTION, _handle_log_action, schema=LOG_ACTION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FROST_DATES,
        _handle_set_frost_dates,
        schema=SET_FROST_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_PLANT_DATA, _handle_refresh_plant_data
    )


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    """Remove services when the last entry unloads."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    for service in (
        SERVICE_LOG_ACTION,
        SERVICE_SET_FROST_DATES,
        SERVICE_REFRESH_PLANT_DATA,
    ):
        hass.services.async_remove(DOMAIN, service)