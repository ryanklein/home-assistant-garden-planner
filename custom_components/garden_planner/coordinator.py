"""Coordinator that recomputes the garden schedule from stored state."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_FIRST_FROST,
    CONF_LAST_FROST,
    DOMAIN,
    EVENT_STAGE_CHANGE,
    EVENT_TASK_DUE,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
    UPDATE_INTERVAL_HOURS,
)
from .frost import resolve_frost_dates
from .models import Bed, GardenTask, Planting, Stage
from .schedule import FrostDates, ScheduleResult, compute_schedule
from .store import GardenStore

if TYPE_CHECKING:
    from . import GardenConfigEntry

_LOGGER = logging.getLogger(__name__)


class GardenData:
    """Computed snapshot exposed to entities."""

    def __init__(self) -> None:
        self.beds: dict[str, Bed] = {}
        self.plantings: dict[str, Planting] = {}
        self.schedules: dict[str, ScheduleResult] = {}
        self.frost: dict[int, FrostDates] = {}

    @property
    def tasks(self) -> list[GardenTask]:
        """All upcoming tasks across every planting, sorted by due date."""
        out: list[GardenTask] = []
        for result in self.schedules.values():
            out.extend(result.tasks)
        return sorted(out, key=lambda t: t.due_date)

    def bed_plantings(self, bed_id: str) -> list[Planting]:
        return [p for p in self.plantings.values() if p.bed_id == bed_id]


class GardenCoordinator(DataUpdateCoordinator[GardenData]):
    """Rebuilds beds/plantings from subentries and recomputes their schedules."""

    config_entry: GardenConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: GardenStore,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
            config_entry=entry,
        )
        self.store = store
        self._prev_stage: dict[str, Stage] = {}

    def _frost_for(self, year: int) -> FrostDates:
        options = self.config_entry.options
        last_override = _parse_date(options.get(CONF_LAST_FROST))
        first_override = _parse_date(options.get(CONF_FIRST_FROST))
        return resolve_frost_dates(
            self.hass.config.latitude, year, last_override, first_override
        )

    def _build_planting(self, subentry: ConfigSubentry) -> Planting:
        planting = Planting.from_dict({**subentry.data, "id": subentry.subentry_id})
        planting.action_log = self.store.get_actions(subentry.subentry_id)
        return planting

    async def _async_update_data(self) -> GardenData:
        data = GardenData()
        today = dt_util.now().date()

        for subentry in self.config_entry.subentries.values():
            if subentry.subentry_type == SUBENTRY_TYPE_BED:
                bed = Bed.from_dict(
                    {**subentry.data, "id": subentry.subentry_id}
                )
                data.beds[bed.id] = bed
            elif subentry.subentry_type == SUBENTRY_TYPE_PLANTING:
                planting = self._build_planting(subentry)
                data.plantings[planting.id] = planting

        for planting in data.plantings.values():
            year = planting.season_year or today.year
            if year not in data.frost:
                data.frost[year] = self._frost_for(year)
            result = compute_schedule(planting, data.frost[year], today)
            data.schedules[planting.id] = result
            self._emit_events(planting.id, result, today)

        # Ensure the current year's frost dates are always available for sensors.
        data.frost.setdefault(today.year, self._frost_for(today.year))
        return data

    def _emit_events(
        self, planting_id: str, result: ScheduleResult, today: date
    ) -> None:
        previous = self._prev_stage.get(planting_id)
        if previous is not None and previous != result.stage:
            self.hass.bus.async_fire(
                EVENT_STAGE_CHANGE,
                {
                    "planting_id": planting_id,
                    "from": previous.value,
                    "to": result.stage.value,
                },
            )
        self._prev_stage[planting_id] = result.stage

        if result.next_task and result.next_task.due_date == today:
            self.hass.bus.async_fire(
                EVENT_TASK_DUE,
                {
                    "planting_id": planting_id,
                    "kind": result.next_task.kind,
                    "label": result.next_task.label,
                },
            )


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
