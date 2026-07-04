# SPDX-License-Identifier: AGPL-3.0-only
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
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_KINDS,
    CONF_FIRST_FROST,
    CONF_LAST_FROST,
    CONF_PROVIDER,
    CONF_API_KEY,
    CONF_API_KEY_SECRET,
    DEFAULT_PROVIDER,
    DOMAIN,
    SERVICE_ARCHIVE_PLANTING,
    SERVICE_CLONE_TO_NEXT_SEASON,
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

TARGET_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("planting_id"): cv.string,
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
        options.get(CONF_API_KEY_SECRET),
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


def _bed_name(entry: GardenConfigEntry, bed_id: str) -> str | None:
    sub = entry.subentries.get(bed_id)
    return sub.data.get("name") if sub is not None else None


async def _handle_archive_planting(call: ServiceCall) -> None:
    """Summarize a planting into the history archive and remove it."""
    hass = call.hass
    entry = _garden_entry(hass)
    planting_ids = _planting_ids_from_call(hass, call)
    if not planting_ids:
        raise ServiceValidationError("No planting targeted for archive_planting")

    coordinator = entry.runtime_data.coordinator
    store = entry.runtime_data.store
    for planting_id in planting_ids:
        subentry = entry.subentries.get(planting_id)
        if subentry is None:
            raise ServiceValidationError(f"Unknown planting: {planting_id}")

        data = subentry.data
        profile = data.get("profile", {})
        schedule = coordinator.data.schedules.get(planting_id)
        record = {
            "planting_id": planting_id,
            "reason": "archived",
            "archived_on": dt_util.now().date().isoformat(),
            "title": subentry.title,
            "season_year": data.get("season_year"),
            "season_label": schedule.season_label if schedule else None,
            "source_id": profile.get("source_id"),
            "common_name": profile.get("common_name"),
            "bed_id": data.get("bed_id"),
            "bed_name": _bed_name(entry, data.get("bed_id", "")),
            "sow_date": schedule.sow_date.isoformat()
            if schedule and schedule.sow_date
            else None,
            "first_harvest_date": schedule.first_harvest_date.isoformat()
            if schedule and schedule.first_harvest_date
            else None,
            "action_log": [e.to_dict() for e in store.get_actions(planting_id)],
        }
        await store.async_archive(record)
        hass.config_entries.async_remove_subentry(entry, planting_id)


async def _handle_clone_to_next_season(call: ServiceCall) -> None:
    """Duplicate a planting into the next season (year + 1), fresh state."""
    hass = call.hass
    entry = _garden_entry(hass)
    planting_ids = _planting_ids_from_call(hass, call)
    if not planting_ids:
        raise ServiceValidationError("No planting targeted for clone_to_next_season")

    for planting_id in planting_ids:
        subentry = entry.subentries.get(planting_id)
        if subentry is None:
            raise ServiceValidationError(f"Unknown planting: {planting_id}")

        data = dict(subentry.data)
        next_year = (data.get("season_year") or dt_util.now().year) + 1
        data["season_year"] = next_year
        data["manual_overrides"] = {}
        common = data.get("profile", {}).get("common_name", "Planting")
        bed_name = _bed_name(entry, data.get("bed_id", ""))
        base = f"{common} — {bed_name}" if bed_name else common
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=data,
                subentry_type=SUBENTRY_TYPE_PLANTING,
                title=f"{base} ({next_year})",
                unique_id=None,
            ),
        )


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
    hass.services.async_register(
        DOMAIN,
        SERVICE_ARCHIVE_PLANTING,
        _handle_archive_planting,
        schema=TARGET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLONE_TO_NEXT_SEASON,
        _handle_clone_to_next_season,
        schema=TARGET_SCHEMA,
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
        SERVICE_ARCHIVE_PLANTING,
        SERVICE_CLONE_TO_NEXT_SEASON,
    ):
        hass.services.async_remove(DOMAIN, service)