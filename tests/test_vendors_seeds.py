# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the vendor -> seed -> planting flow and models."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_planner.const import (
    ADD_NEW,
    CONF_PROVIDER,
    DEFAULT_PROVIDER,
    DOMAIN,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
    SUBENTRY_TYPE_SEED,
    SUBENTRY_TYPE_VENDOR,
    VENDOR_UNKNOWN_ID,
    VENDOR_UNKNOWN_NAME,
)
from custom_components.garden_planner.models import PlantProfile, Seed, Vendor

from homeassistant.config_entries import ConfigSubentryData


async def _setup(hass: HomeAssistant) -> tuple[MockConfigEntry, str]:
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


def _subs(entry, kind):
    return [s for s in entry.subentries.values() if s.subentry_type == kind]


async def _add_vendor(hass, entry, name="Baker Creek") -> str:
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_VENDOR), context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": name, "url": "https://example.com"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return next(
        sid
        for sid, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_TYPE_VENDOR and sub.data["name"] == name
    )


# --- Model round-trips ------------------------------------------------------


def test_vendor_roundtrip():
    v = Vendor(id="v1", name="Baker Creek", url="https://x", notes="heirloom")
    assert Vendor.from_dict(v.to_dict()) == v


def test_seed_roundtrip():
    seed = Seed(
        id="s1",
        vendor_id="v1",
        vendor_name="Baker Creek",
        variety="Cherokee Purple",
        profile=PlantProfile(
            common_name="Tomato", source="bundled", source_id="tomato"
        ),
        sku="TOM-123",
    )
    restored = Seed.from_dict(seed.to_dict())
    assert restored == seed
    assert restored.profile.common_name == "Tomato"


# --- Vendor flow ------------------------------------------------------------


async def test_vendor_flow_creates_vendor(hass: HomeAssistant) -> None:
    entry, _ = await _setup(hass)
    await _add_vendor(hass, entry, "Johnny's Seeds")
    vendors = _subs(entry, SUBENTRY_TYPE_VENDOR)
    assert [v.data["name"] for v in vendors] == ["Johnny's Seeds"]


# --- Seed flow --------------------------------------------------------------


async def test_seed_flow_with_existing_vendor(hass: HomeAssistant) -> None:
    entry, _ = await _setup(hass)
    vendor_id = await _add_vendor(hass, entry, "Baker Creek")

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SEED), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"vendor_id": vendor_id, "plant_query": "tomato", "variety": "Cherokee Purple"},
    )
    assert result["step_id"] == "pick"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"plant_source_id": "tomato"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    seed = _subs(entry, SUBENTRY_TYPE_SEED)[0]
    assert seed.data["vendor_id"] == vendor_id
    assert seed.data["vendor_name"] == "Baker Creek"
    assert seed.data["variety"] == "Cherokee Purple"
    assert seed.data["profile"]["common_name"] == "Tomato"
    assert "Cherokee Purple" in seed.title and "Baker Creek" in seed.title


async def test_seed_flow_saved_unknown_vendor(hass: HomeAssistant) -> None:
    entry, _ = await _setup(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SEED), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"vendor_id": VENDOR_UNKNOWN_ID, "plant_query": "basil", "variety": "Genovese"},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"plant_source_id": "basil"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    seed = _subs(entry, SUBENTRY_TYPE_SEED)[0]
    assert seed.data["vendor_id"] == VENDOR_UNKNOWN_ID
    assert seed.data["vendor_name"] == VENDOR_UNKNOWN_NAME


# --- Planting wizard --------------------------------------------------------


async def test_planting_wizard_inline_add_seed(hass: HomeAssistant) -> None:
    """vendor(new) -> seed(add new, search) -> details -> planting; a seed is
    created and the planting references it."""
    entry, bed_id = await _setup(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PLANTING), context={"source": "user"}
    )
    assert result["step_id"] == "vendor"
    # Add a new vendor inline.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"vendor_id": ADD_NEW}
    )
    assert result["step_id"] == "vendor_new"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Territorial"}
    )
    assert result["step_id"] == "seed"
    # No seeds for this vendor yet -> add a new seed.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"seed_id": ADD_NEW}
    )
    assert result["step_id"] == "seed_new"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"plant_query": "tomato", "variety": "Sungold"}
    )
    assert result["step_id"] == "seed_pick"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"plant_source_id": "tomato"}
    )
    assert result["step_id"] == "details"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "bed_id": bed_id,
            "quantity": 2,
            "season_year": 2026,
            "successions": 1,
            "succession_interval_days": 14,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert len(_subs(entry, SUBENTRY_TYPE_VENDOR)) == 1
    assert len(_subs(entry, SUBENTRY_TYPE_SEED)) == 1
    planting = _subs(entry, SUBENTRY_TYPE_PLANTING)[0]
    seed = _subs(entry, SUBENTRY_TYPE_SEED)[0]
    assert planting.data["seed_id"] == seed.subentry_id
    assert planting.data["seed_variety"] == "Sungold"
    assert planting.data["vendor_name"] == "Territorial"
    assert planting.data["profile"]["common_name"] == "Tomato"
    assert planting.title.startswith("Sungold Tomato")
