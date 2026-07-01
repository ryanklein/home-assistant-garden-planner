"""Buttons to log garden actions on a planting."""

from __future__ import annotations

import homeassistant.util.dt as dt_util
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GardenConfigEntry
from .const import ACTION_HARVEST, ACTION_TRANSPLANT, ACTION_WATER
from .coordinator import GardenCoordinator
from .entity import GardenPlantingEntity

# Actions exposed as one-tap buttons on every planting device.
LOG_BUTTONS = (ACTION_WATER, ACTION_TRANSPLANT, ACTION_HARVEST)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up log buttons for every planting."""
    coordinator = entry.runtime_data.coordinator
    entities: list[ButtonEntity] = []
    for planting_id in coordinator.data.plantings:
        entities.extend(
            LogActionButton(coordinator, planting_id, kind) for kind in LOG_BUTTONS
        )
    async_add_entities(entities)


class LogActionButton(GardenPlantingEntity, ButtonEntity):
    """Records an action (with today's date) when pressed."""

    def __init__(
        self, coordinator: GardenCoordinator, planting_id: str, kind: str
    ) -> None:
        super().__init__(coordinator, planting_id)
        self._kind = kind
        self._attr_translation_key = f"log_{kind}"
        self._attr_unique_id = f"{planting_id}_log_{kind}"

    async def async_press(self) -> None:
        await self.coordinator.store.async_add_action(
            self._planting_id, self._kind, dt_util.now().date()
        )
        await self.coordinator.async_request_refresh()
