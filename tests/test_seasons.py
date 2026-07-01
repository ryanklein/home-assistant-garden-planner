# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the season lifecycle: archive, clone and history retention."""

from __future__ import annotations

from datetime import date

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_planner.const import (
    CONF_PROVIDER,
    DEFAULT_PROVIDER,
    DOMAIN,
    SERVICE_ARCHIVE_PLANTING,
    SERVICE_CLONE_TO_NEXT_SEASON,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
)

_PROFILE = {
    "common_name": "Beet",
    "source": DEFAULT_PROVIDER,
    "source_id": "beet",
    "method": "direct",
    "days_to_maturity": 55,
    "sow_weeks_before_last_frost": 4,
    "water": "medium",
}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        options={CONF_PROVIDER: DEFAULT_PROVIDER},
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_BED,
                title="Raised Bed 1",
                unique_id=None,
                data={"name": "Raised Bed 1", "sun_exposure": "full"},
            ),
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_PLANTING,
                title="Beet",
                unique_id=None,
                data={
                    "bed_id": "bed1",
                    "profile": _PROFILE,
                    "method": "direct",
                    "quantity": 1,
                    "season_year": 2026,
                    "manual_overrides": {},
                },
            ),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _planting_id(entry: MockConfigEntry) -> str:
    return next(
        sid
        for sid, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_PLANTING
    )


async def test_archive_planting_stores_history_and_removes(
    hass: HomeAssistant,
) -> None:
    entry = await _setup(hass)
    planting_id = _planting_id(entry)
    store = entry.runtime_data.store
    # Log a harvest so there is history to preserve.
    await store.async_add_action(planting_id, "harvest", date(2026, 7, 1))

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ARCHIVE_PLANTING,
        {"planting_id": planting_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Subentry gone; archive holds a record with the harvest history.
    assert planting_id not in entry.subentries
    archive = store.get_archive()
    assert len(archive) == 1
    assert archive[0]["common_name"] == "Beet"
    assert archive[0]["season_year"] == 2026
    assert any(a["kind"] == "harvest" for a in archive[0]["action_log"])


async def test_clone_to_next_season(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    planting_id = _planting_id(entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLONE_TO_NEXT_SEASON,
        {"planting_id": planting_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    plantings = [
        sub
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TYPE_PLANTING
    ]
    assert len(plantings) == 2
    years = sorted(sub.data["season_year"] for sub in plantings)
    assert years == [2026, 2027]
    assert any("(2027)" in sub.title for sub in plantings)


async def test_orphaned_history_is_reconciled(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    planting_id = _planting_id(entry)
    store = entry.runtime_data.store
    await store.async_add_action(planting_id, "water", date(2026, 6, 1))

    # Remove the planting directly (as the UI would), bypassing the service.
    # This triggers a reload, which rebuilds runtime_data with a fresh store
    # that loads the persisted (now-orphaned) action log and reconciles it.
    hass.config_entries.async_remove_subentry(entry, planting_id)
    await hass.async_block_till_done()

    archive = entry.runtime_data.store.get_archive()
    assert any(rec.get("reason") == "orphaned" for rec in archive)
    assert planting_id not in entry.subentries
