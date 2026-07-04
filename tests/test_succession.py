# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the succession-planting helper and name disambiguation."""

from __future__ import annotations

from datetime import date

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_planner.const import (
    CONF_PROVIDER,
    DEFAULT_PROVIDER,
    DOMAIN,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
    SUBENTRY_TYPE_SEED,
    VENDOR_UNKNOWN_ID,
)


async def _setup_with_bed(hass: HomeAssistant) -> tuple[MockConfigEntry, str]:
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
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    bed_id = next(
        sid
        for sid, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_BED
    )
    return entry, bed_id


async def _add_seed(hass, entry, *, variety="Detroit", query="beet", source_id="beet"):
    """Create a seed (from the 'Saved/Unknown' vendor) and return its id."""
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SEED), context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"vendor_id": VENDOR_UNKNOWN_ID, "plant_query": query, "variety": variety},
    )
    assert result["step_id"] == "pick"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"plant_source_id": source_id}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return next(
        sid
        for sid, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_SEED
    )


async def _add_planting(hass, entry, bed_id, seed_id, *, successions, interval=14):
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PLANTING), context={"source": "user"}
    )
    assert result["step_id"] == "vendor"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"vendor_id": VENDOR_UNKNOWN_ID}
    )
    assert result["step_id"] == "seed"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"seed_id": seed_id}
    )
    assert result["step_id"] == "details"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "bed_id": bed_id,
            "quantity": 1,
            "season_year": 2026,
            "successions": successions,
            "succession_interval_days": interval,
        },
    )
    await hass.async_block_till_done()
    return result


async def test_succession_creates_staggered_plantings(hass: HomeAssistant) -> None:
    entry, bed_id = await _setup_with_bed(hass)
    seed_id = await _add_seed(hass, entry)
    result = await _add_planting(
        hass, entry, bed_id, seed_id, successions=3, interval=14
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    plantings = [
        sub
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TYPE_PLANTING
    ]
    assert len(plantings) == 3

    # Titles are distinguishable and include the variety.
    titles = sorted(sub.title for sub in plantings)
    assert titles == [
        "Detroit Beet — Raised Bed 1 #1",
        "Detroit Beet — Raised Bed 1 #2",
        "Detroit Beet — Raised Bed 1 #3",
    ]

    # Sow overrides are staggered by the interval.
    sow_dates = sorted(
        date.fromisoformat(sub.data["manual_overrides"]["sow"]) for sub in plantings
    )
    assert (sow_dates[1] - sow_dates[0]).days == 14
    assert (sow_dates[2] - sow_dates[1]).days == 14


async def test_duplicate_single_planting_gets_dated_title(
    hass: HomeAssistant,
) -> None:
    entry, bed_id = await _setup_with_bed(hass)
    seed_id = await _add_seed(hass, entry)
    # First single planting: plain title.
    await _add_planting(hass, entry, bed_id, seed_id, successions=1)
    # Second single planting of same crop/bed: title disambiguated with a date.
    await _add_planting(hass, entry, bed_id, seed_id, successions=1)

    plantings = [
        sub
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TYPE_PLANTING
    ]
    assert len(plantings) == 2
    titles = [sub.title for sub in plantings]
    assert "Detroit Beet — Raised Bed 1" in titles
    assert any(t.startswith("Detroit Beet — Raised Bed 1 (2026-") for t in titles)
