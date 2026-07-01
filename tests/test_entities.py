# SPDX-License-Identifier: AGPL-3.0-only
"""End-to-end test: subentries produce devices, entities and tasks."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_planner.const import (
    CONF_PROVIDER,
    DEFAULT_PROVIDER,
    DOMAIN,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
)

_TOMATO_PROFILE = {
    "common_name": "Tomato",
    "source": DEFAULT_PROVIDER,
    "source_id": "tomato",
    "method": "transplant",
    "days_to_maturity": 65,
    "sow_weeks_before_last_frost": 6,
    "transplant_weeks_after_last_frost": 2,
    "water": "medium",
    "harvest_window_days": 60,
}


async def _setup_with_planting(hass: HomeAssistant) -> MockConfigEntry:
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
                    "profile": _TOMATO_PROFILE,
                    "method": "transplant",
                    "quantity": 3,
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


async def test_planting_creates_entities(hass: HomeAssistant) -> None:
    entry = await _setup_with_planting(hass)

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    by_domain = {e.entity_id.split(".")[0] for e in entities}

    # Every platform should have contributed at least one entity.
    assert {"sensor", "binary_sensor", "button", "calendar", "todo"} <= by_domain
    assert any(e.unique_id.endswith("_stage") for e in entities)


async def test_calendar_and_todo_have_tasks(hass: HomeAssistant) -> None:
    await _setup_with_planting(hass)

    calendar_ids = hass.states.async_entity_ids("calendar")
    assert calendar_ids
    todo_ids = hass.states.async_entity_ids("todo")
    assert todo_ids
    # The to-do list should report a non-zero count of upcoming tasks.
    todo_state = hass.states.get(todo_ids[0])
    assert int(todo_state.state) > 0


async def test_stage_sensor_has_value(hass: HomeAssistant) -> None:
    await _setup_with_planting(hass)
    stage_ids = [
        eid
        for eid in hass.states.async_entity_ids("sensor")
        if "stage" in eid
    ]
    assert stage_ids
    assert hass.states.get(stage_ids[0]).state != "unknown"
