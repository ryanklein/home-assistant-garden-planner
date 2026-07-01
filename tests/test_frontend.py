# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the Lovelace card serving and the sensor attributes it reads."""

from __future__ import annotations

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_planner.const import (
    CONF_PROVIDER,
    DEFAULT_PROVIDER,
    DOMAIN,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
)

_PROFILE = {
    "common_name": "Tomato",
    "source": DEFAULT_PROVIDER,
    "source_id": "tomato",
    "method": "transplant",
    "days_to_maturity": 65,
    "sow_weeks_before_last_frost": 6,
    "transplant_weeks_after_last_frost": 2,
    "water": "medium",
}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    # The compiled `hass_frontend` package isn't pip-installable, so `frontend`
    # can't fully set up here. Seed the pieces our code touches so the real
    # registration path runs (in production `frontend` is always loaded).
    hass.data.setdefault(DATA_EXTRA_MODULE_URL, set())
    hass.config.components.add("frontend")

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
                title="Tomato",
                unique_id=None,
                data={
                    "bed_id": "bed1",
                    "profile": _PROFILE,
                    "method": "transplant",
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


async def test_card_module_is_registered(hass: HomeAssistant) -> None:
    await _setup(hass)
    urls = hass.data[DATA_EXTRA_MODULE_URL]
    assert any("garden-planner-card.js" in u for u in urls)


async def test_stage_sensor_exposes_schedule_attributes(
    hass: HomeAssistant,
) -> None:
    await _setup(hass)
    stage = next(
        hass.states.get(eid)
        for eid in hass.states.async_entity_ids("sensor")
        if eid.endswith("_stage")
    )
    attrs = stage.attributes
    assert attrs["gp_role"] == "planting"
    assert attrs["plant"] == "Tomato"
    assert attrs["sow_date"]  # frost-relative sow date is populated
    assert attrs["first_harvest_date"]
    assert "season" in attrs
