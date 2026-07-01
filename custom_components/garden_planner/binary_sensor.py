# SPDX-License-Identifier: AGPL-3.0-only
"""Binary sensors for Garden Planner."""

from __future__ import annotations

import homeassistant.util.dt as dt_util
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GardenConfigEntry
from .coordinator import GardenCoordinator
from .entity import GardenPlantingEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up an 'action needed today' binary sensor per planting."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ActionNeededBinarySensor(coordinator, planting_id)
        for planting_id in coordinator.data.plantings
    )


class ActionNeededBinarySensor(GardenPlantingEntity, BinarySensorEntity):
    """On when a planting has a task due today or overdue."""

    _attr_translation_key = "action_needed"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: GardenCoordinator, planting_id: str) -> None:
        super().__init__(coordinator, planting_id)
        self._attr_unique_id = f"{planting_id}_action_needed"

    @property
    def is_on(self) -> bool:
        schedule = self.schedule
        if schedule is None or schedule.next_task is None:
            return False
        return schedule.next_task.due_date <= dt_util.now().date()

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        schedule = self.schedule
        if schedule is None or schedule.next_task is None:
            return {}
        return {
            "task": schedule.next_task.kind,
            "due_date": schedule.next_task.due_date.isoformat(),
        }
