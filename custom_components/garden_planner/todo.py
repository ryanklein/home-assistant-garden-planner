"""A to-do list of upcoming garden tasks.

Checking an item off records the corresponding action against the planting (with
today's date), which advances its schedule.
"""

from __future__ import annotations

import homeassistant.util.dt as dt_util
from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GardenConfigEntry
from .const import DOMAIN
from .coordinator import GardenCoordinator
from .models import GardenTask

_UID_SEP = "|"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the single garden to-do list."""
    async_add_entities(
        [GardenTodoList(entry.runtime_data.coordinator, entry.entry_id)]
    )


class GardenTodoList(CoordinatorEntity[GardenCoordinator], TodoListEntity):
    """Upcoming garden tasks as a native to-do list."""

    _attr_has_entity_name = True
    _attr_translation_key = "tasks"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, coordinator: GardenCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_tasks"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "Garden",
            "manufacturer": "Garden Planner",
            "model": "Garden",
        }

    def _uid(self, task: GardenTask) -> str:
        return _UID_SEP.join(
            [task.planting_id, task.kind, task.due_date.isoformat()]
        )

    def _item_from_task(self, task: GardenTask) -> TodoItem:
        planting = self.coordinator.data.plantings.get(task.planting_id)
        name = planting.profile.common_name if planting else "Planting"
        return TodoItem(
            uid=self._uid(task),
            summary=f"{task.label or task.kind}: {name}",
            status=TodoItemStatus.NEEDS_ACTION,
            due=task.due_date,
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        return [self._item_from_task(task) for task in self.coordinator.data.tasks]

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Completing an item logs the matching action against the planting."""
        if item.status != TodoItemStatus.COMPLETED or not item.uid:
            return
        planting_id, kind, _ = item.uid.split(_UID_SEP)
        if planting_id not in self.coordinator.data.plantings:
            return
        await self.coordinator.store.async_add_action(
            planting_id, kind, dt_util.now().date()
        )
        await self.coordinator.async_request_refresh()
