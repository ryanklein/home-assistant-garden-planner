# SPDX-License-Identifier: AGPL-3.0-only
"""Sensor entities for Garden Planner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GardenConfigEntry
from .const import DOMAIN
from .coordinator import GardenCoordinator
from .entity import GardenBedEntity, GardenPlantingEntity
from .models import Stage
from .schedule import ScheduleResult


@dataclass(frozen=True, kw_only=True)
class PlantingSensorDescription(SensorEntityDescription):
    """Describes a per-planting sensor derived from its schedule."""

    value_fn: Callable[[ScheduleResult, date], object]


def _days_until(target: date | None, today: date) -> int | None:
    return (target - today).days if target is not None else None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


PLANTING_SENSORS: tuple[PlantingSensorDescription, ...] = (
    PlantingSensorDescription(
        key="stage",
        translation_key="stage",
        device_class=SensorDeviceClass.ENUM,
        options=[s.value for s in Stage],
        value_fn=lambda s, today: s.stage.value,
    ),
    PlantingSensorDescription(
        key="season",
        translation_key="season",
        value_fn=lambda s, today: s.season_label,
    ),
    PlantingSensorDescription(
        key="next_task",
        translation_key="next_task",
        value_fn=lambda s, today: s.next_task.kind if s.next_task else None,
    ),
    PlantingSensorDescription(
        key="next_task_date",
        translation_key="next_task_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda s, today: s.next_task.due_date if s.next_task else None,
    ),
    PlantingSensorDescription(
        key="days_to_next_task",
        translation_key="days_to_next_task",
        native_unit_of_measurement="d",
        value_fn=lambda s, today: (
            _days_until(s.next_task.due_date, today) if s.next_task else None
        ),
    ),
    PlantingSensorDescription(
        key="harvest_date",
        translation_key="harvest_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda s, today: s.first_harvest_date,
    ),
    PlantingSensorDescription(
        key="days_to_harvest",
        translation_key="days_to_harvest",
        native_unit_of_measurement="d",
        value_fn=lambda s, today: _days_until(s.first_harvest_date, today),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for every planting, bed and the garden itself."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = []

    # Add bed entities first so their devices exist before plantings reference
    # them as a `via_device` parent.
    for bed_id in coordinator.data.beds:
        entities.append(BedPlantingCountSensor(coordinator, bed_id))

    for planting_id in coordinator.data.plantings:
        entities.extend(
            PlantingSensor(coordinator, planting_id, description)
            for description in PLANTING_SENSORS
        )

    entities.append(FrostSensor(coordinator, entry.entry_id, "last"))
    entities.append(FrostSensor(coordinator, entry.entry_id, "first"))

    async_add_entities(entities)


class PlantingSensor(GardenPlantingEntity, SensorEntity):
    """A schedule-derived sensor for a single planting."""

    entity_description: PlantingSensorDescription

    def __init__(
        self,
        coordinator: GardenCoordinator,
        planting_id: str,
        description: PlantingSensorDescription,
    ) -> None:
        super().__init__(coordinator, planting_id)
        self.entity_description = description
        self._attr_unique_id = f"{planting_id}_{description.key}"

    @property
    def native_value(self) -> object:
        schedule = self.schedule
        if schedule is None:
            return None
        return self.entity_description.value_fn(schedule, dt_util.now().date())

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        # The 'stage' sensor carries the full schedule so the Lovelace card can
        # read one entity per planting instead of stitching several together.
        if self.entity_description.key != "stage":
            return None
        planting = self.planting
        schedule = self.schedule
        if planting is None or schedule is None:
            return None
        bed = self.coordinator.data.beds.get(planting.bed_id)
        return {
            "gp_role": "planting",
            "planting_id": planting.id,
            "plant": planting.profile.common_name,
            "bed": bed.name if bed else None,
            "bed_id": planting.bed_id,
            "season": schedule.season_label,
            "sow_date": _iso(schedule.sow_date),
            "transplant_date": _iso(schedule.transplant_date),
            "first_harvest_date": _iso(schedule.first_harvest_date),
            "harvest_end_date": _iso(schedule.harvest_end_date),
            "next_task": schedule.next_task.kind if schedule.next_task else None,
            "next_task_date": _iso(
                schedule.next_task.due_date if schedule.next_task else None
            ),
        }


class BedPlantingCountSensor(GardenBedEntity, SensorEntity):
    """Number of active plantings in a bed."""

    _attr_translation_key = "active_plantings"
    _attr_native_unit_of_measurement = "plantings"

    def __init__(self, coordinator: GardenCoordinator, bed_id: str) -> None:
        super().__init__(coordinator, bed_id)
        self._attr_unique_id = f"{bed_id}_active_plantings"

    @property
    def native_value(self) -> int:
        active = 0
        for planting in self.coordinator.data.bed_plantings(self._bed_id):
            result = self.coordinator.data.schedules.get(planting.id)
            if result is not None and result.stage is not Stage.DONE:
                active += 1
        return active


class FrostSensor(SensorEntity):
    """Estimated (or overridden) last/first frost date for the current year."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self, coordinator: GardenCoordinator, entry_id: str, which: str
    ) -> None:
        self._coordinator = coordinator
        self._which = which
        self._attr_translation_key = f"{which}_frost"
        self._attr_unique_id = f"{entry_id}_{which}_frost"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "Garden",
            "manufacturer": "Garden Planner",
            "model": "Garden",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> date | None:
        year = dt_util.now().date().year
        frost = self._coordinator.data.frost.get(year)
        if frost is None:
            return None
        return frost.last_frost if self._which == "last" else frost.first_frost
