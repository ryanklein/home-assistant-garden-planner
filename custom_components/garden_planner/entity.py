"""Shared entity base classes and device wiring for Garden Planner."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenCoordinator
from .models import Bed, Planting
from .schedule import ScheduleResult


class GardenBaseEntity(CoordinatorEntity[GardenCoordinator]):
    """Common base wiring for all Garden Planner entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GardenCoordinator) -> None:
        super().__init__(coordinator)


class GardenBedEntity(GardenBaseEntity):
    """Entity attached to a garden bed device."""

    def __init__(self, coordinator: GardenCoordinator, bed_id: str) -> None:
        super().__init__(coordinator)
        self._bed_id = bed_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, bed_id)},
            name=self.bed.name if self.bed else "Garden bed",
            manufacturer="Garden Planner",
            model="Garden bed",
        )

    @property
    def bed(self) -> Bed | None:
        return self.coordinator.data.beds.get(self._bed_id)

    @property
    def available(self) -> bool:
        return super().available and self.bed is not None


class GardenPlantingEntity(GardenBaseEntity):
    """Entity attached to a planting device (nested under its bed)."""

    def __init__(self, coordinator: GardenCoordinator, planting_id: str) -> None:
        super().__init__(coordinator)
        self._planting_id = planting_id
        planting = self.planting
        bed_id = planting.bed_id if planting else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, planting_id)},
            name=planting.profile.common_name if planting else "Planting",
            manufacturer="Garden Planner",
            model="Planting",
            via_device=(DOMAIN, bed_id) if bed_id else None,
        )

    @property
    def planting(self) -> Planting | None:
        return self.coordinator.data.plantings.get(self._planting_id)

    @property
    def schedule(self) -> ScheduleResult | None:
        return self.coordinator.data.schedules.get(self._planting_id)

    @property
    def available(self) -> bool:
        return super().available and self.planting is not None
