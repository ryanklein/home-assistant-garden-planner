# SPDX-License-Identifier: AGPL-3.0-only
"""Date entities for manually overriding a planting's key dates."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GardenConfigEntry
from .const import ACTION_HARVEST, ACTION_SOW, ACTION_TRANSPLANT
from .coordinator import GardenCoordinator
from .entity import GardenPlantingEntity

# Which computed dates the gardener may override, by action kind.
OVERRIDE_KINDS = (ACTION_SOW, ACTION_TRANSPLANT, ACTION_HARVEST)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up override-date entities for every planting."""
    coordinator = entry.runtime_data.coordinator
    entities: list[DateEntity] = []
    for planting_id in coordinator.data.plantings:
        entities.extend(
            OverrideDateEntity(coordinator, planting_id, kind)
            for kind in OVERRIDE_KINDS
        )
    async_add_entities(entities)


class OverrideDateEntity(GardenPlantingEntity, DateEntity):
    """A manual override for one of a planting's computed dates."""

    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: GardenCoordinator, planting_id: str, kind: str
    ) -> None:
        super().__init__(coordinator, planting_id)
        self._kind = kind
        self._attr_translation_key = f"override_{kind}"
        self._attr_unique_id = f"{planting_id}_override_{kind}"

    @property
    def native_value(self) -> date | None:
        planting = self.planting
        return planting.override_date(self._kind) if planting else None

    async def async_set_value(self, value: date) -> None:
        await self._write_override(value.isoformat())

    async def _write_override(self, iso_value: str | None) -> None:
        entry = self.coordinator.config_entry
        subentry = entry.subentries.get(self._planting_id)
        if subentry is None:
            return
        overrides = dict(subentry.data.get("manual_overrides", {}))
        if iso_value is None:
            overrides.pop(self._kind, None)
        else:
            overrides[self._kind] = iso_value
        new_data = {**subentry.data, "manual_overrides": overrides}
        self.hass.config_entries.async_update_subentry(entry, subentry, data=new_data)
