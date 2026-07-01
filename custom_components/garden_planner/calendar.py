"""A calendar of upcoming garden tasks."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import homeassistant.util.dt as dt_util
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GardenConfigEntry
from .const import DOMAIN
from .coordinator import GardenCoordinator
from .models import GardenTask


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the single garden calendar."""
    async_add_entities(
        [GardenCalendar(entry.runtime_data.coordinator, entry.entry_id)]
    )


class GardenCalendar(CoordinatorEntity[GardenCoordinator], CalendarEntity):
    """Exposes every planting's upcoming tasks as calendar events."""

    _attr_has_entity_name = True
    _attr_translation_key = "garden"

    def __init__(self, coordinator: GardenCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_calendar"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "Garden",
            "manufacturer": "Garden Planner",
            "model": "Garden",
        }

    def _event_from_task(self, task: GardenTask) -> CalendarEvent:
        planting = self.coordinator.data.plantings.get(task.planting_id)
        name = planting.profile.common_name if planting else "Planting"
        bed = self.coordinator.data.beds.get(planting.bed_id) if planting else None
        return CalendarEvent(
            start=task.due_date,
            end=task.due_date + timedelta(days=1),
            summary=f"{task.label or task.kind}: {name}",
            description=f"Bed: {bed.name}" if bed else None,
            uid=f"{task.planting_id}_{task.kind}_{task.due_date.isoformat()}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        upcoming = [t for t in self.coordinator.data.tasks if t.due_date >= today]
        return self._event_from_task(upcoming[0]) if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start = start_date.date()
        end = end_date.date()
        return [
            self._event_from_task(task)
            for task in self.coordinator.data.tasks
            if start <= task.due_date <= end
        ]
