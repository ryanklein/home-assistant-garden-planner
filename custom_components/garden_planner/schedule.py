"""Frost-relative scheduling logic for the Garden Planner.

Pure functions with no Home Assistant dependencies so the date math can be unit
tested in isolation. Given a plant profile, a planting (with its manual overrides
and action log) and the local frost dates, this derives the sow / transplant /
harvest calendar, the current lifecycle stage, and the next actionable task.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .const import (
    ACTION_HARVEST,
    ACTION_SOW,
    ACTION_TRANSPLANT,
    ACTION_WATER,
    ANCHOR_FALL,
    METHOD_TRANSPLANT,
    WATER_CADENCE_DAYS,
    WATER_MEDIUM,
)
from .models import GardenTask, Planting, PlantProfile, Stage

# Rough biological windows (days) used when a profile lacks explicit data.
GERMINATION_DAYS = 10
SEEDLING_DAYS = 21
TRANSPLANT_ESTABLISH_DAYS = 14
DEFAULT_DAYS_TO_MATURITY = 60


@dataclass(slots=True)
class FrostDates:
    """Resolved local frost dates for a particular growing season."""

    last_frost: date
    first_frost: date


@dataclass(slots=True)
class ScheduleResult:
    """Everything the coordinator/entities need for one planting."""

    sow_date: date | None
    transplant_date: date | None
    first_harvest_date: date | None
    harvest_end_date: date | None
    stage: Stage
    next_task: GardenTask | None
    tasks: list[GardenTask]

    @property
    def season_label(self) -> str | None:
        """A human season label, spanning two years for overwintering crops."""
        if self.sow_date is None:
            return None
        end = self.first_harvest_date or self.sow_date
        if end.year != self.sow_date.year:
            return f"{self.sow_date.year}–{end.year}"
        return str(self.sow_date.year)


def _weeks(value: float | None) -> timedelta | None:
    return timedelta(weeks=value) if value is not None else None


def compute_sow_date(
    profile: PlantProfile, planting: Planting, frost: FrostDates
) -> date | None:
    """Return the effective sow date: override > logged action > computed."""
    if (override := planting.override_date(ACTION_SOW)) is not None:
        return override
    if (logged := planting.last_action(ACTION_SOW)) is not None:
        return logged
    # Fall-anchored (overwintering) crops are sown relative to the first fall
    # frost; everything else relative to the last spring frost.
    anchor = (
        frost.first_frost if profile.sow_anchor == ANCHOR_FALL else frost.last_frost
    )
    offset = _weeks(profile.sow_weeks_before_last_frost)
    if offset is not None:
        return anchor - offset
    # Frost-tolerant crops with no explicit offset can go in around the anchor.
    return anchor


def compute_transplant_date(
    profile: PlantProfile, planting: Planting, frost: FrostDates
) -> date | None:
    """Transplant date for transplant-method plantings (else ``None``)."""
    if planting.method != METHOD_TRANSPLANT:
        return None
    if (override := planting.override_date(ACTION_TRANSPLANT)) is not None:
        return override
    if (logged := planting.last_action(ACTION_TRANSPLANT)) is not None:
        return logged
    offset = _weeks(profile.transplant_weeks_after_last_frost)
    if offset is not None:
        return frost.last_frost + offset
    return frost.last_frost


def compute_harvest_dates(
    profile: PlantProfile,
    planting: Planting,
    sow_date: date | None,
    transplant_date: date | None,
) -> tuple[date | None, date | None]:
    """Return ``(first_harvest, harvest_end)``.

    Days-to-maturity is counted from the transplant date for transplant crops,
    otherwise from the sow date -- matching how seed packets quote the figure.
    """
    if (override := planting.override_date(ACTION_HARVEST)) is not None:
        first = override
    else:
        anchor = (
            transplant_date if profile.method == METHOD_TRANSPLANT else sow_date
        )
        if anchor is None:
            return None, None
        dtm = profile.days_to_maturity or DEFAULT_DAYS_TO_MATURITY
        first = anchor + timedelta(days=dtm)
    end = first + timedelta(days=profile.harvest_window_days)
    return first, end


def compute_stage(
    planting: Planting,
    sow_date: date | None,
    transplant_date: date | None,
    first_harvest: date | None,
    harvest_end: date | None,
    today: date,
) -> Stage:
    """Determine the current lifecycle stage from the calendar + action log."""
    if planting.last_action(ACTION_HARVEST) is not None and (
        harvest_end is None or today > harvest_end
    ):
        return Stage.DONE
    if harvest_end is not None and today > harvest_end:
        return Stage.DONE
    if first_harvest is not None and today >= first_harvest:
        return Stage.HARVESTING

    if sow_date is None or today < sow_date:
        return Stage.PLANNED

    days_since_sow = (today - sow_date).days
    if days_since_sow < GERMINATION_DAYS:
        return Stage.SOWN
    if days_since_sow < GERMINATION_DAYS + SEEDLING_DAYS:
        # Seedlings destined for transplant stay "seedling" until moved.
        if transplant_date is not None and today < transplant_date:
            return Stage.SEEDLING
        return Stage.GERMINATING if days_since_sow < GERMINATION_DAYS + 4 else Stage.SEEDLING

    if transplant_date is not None:
        if today < transplant_date:
            return Stage.SEEDLING
        if (today - transplant_date).days < TRANSPLANT_ESTABLISH_DAYS:
            return Stage.TRANSPLANTED
    return Stage.GROWING


def compute_next_water_date(
    profile: PlantProfile,
    planting: Planting,
    sow_date: date | None,
    harvest_end: date | None,
    today: date,
) -> date | None:
    """Next watering due date, or ``None`` if not applicable right now."""
    if sow_date is None or today < sow_date:
        return None
    if harvest_end is not None and today > harvest_end:
        return None
    # Overwintering crops sit dormant through the cold months; skip automatic
    # watering tasks and let the gardener water manually if needed.
    if profile.overwinter:
        return None
    cadence = WATER_CADENCE_DAYS.get(profile.water, WATER_CADENCE_DAYS[WATER_MEDIUM])
    last_water = planting.last_action(ACTION_WATER)
    anchor = last_water if last_water is not None else sow_date
    due = anchor + timedelta(days=cadence)
    # If we're already overdue, the task is due today.
    return max(due, today) if due < today else due


def compute_schedule(
    planting: Planting, frost: FrostDates, today: date
) -> ScheduleResult:
    """Full schedule for a single planting."""
    profile = planting.profile
    sow_date = compute_sow_date(profile, planting, frost)
    transplant_date = compute_transplant_date(profile, planting, frost)
    first_harvest, harvest_end = compute_harvest_dates(
        profile, planting, sow_date, transplant_date
    )
    stage = compute_stage(
        planting, sow_date, transplant_date, first_harvest, harvest_end, today
    )

    tasks: list[GardenTask] = []
    if sow_date is not None and planting.last_action(ACTION_SOW) is None:
        tasks.append(
            GardenTask(planting.id, ACTION_SOW, sow_date, label="Sow seeds")
        )
    if (
        transplant_date is not None
        and planting.last_action(ACTION_TRANSPLANT) is None
    ):
        tasks.append(
            GardenTask(
                planting.id, ACTION_TRANSPLANT, transplant_date, label="Transplant seedlings"
            )
        )
    if (
        water_date := compute_next_water_date(
            profile, planting, sow_date, harvest_end, today
        )
    ) is not None:
        tasks.append(
            GardenTask(planting.id, ACTION_WATER, water_date, label="Water")
        )
    if first_harvest is not None and stage != Stage.DONE:
        tasks.append(
            GardenTask(
                planting.id, ACTION_HARVEST, first_harvest, label="Begin harvest"
            )
        )

    upcoming = sorted(
        (t for t in tasks if not t.done), key=lambda t: t.due_date
    )
    # The next task is the soonest one that is due today or in the future,
    # falling back to the most overdue task if everything is in the past.
    future = [t for t in upcoming if t.due_date >= today]
    next_task = future[0] if future else (upcoming[0] if upcoming else None)

    return ScheduleResult(
        sow_date=sow_date,
        transplant_date=transplant_date,
        first_harvest_date=first_harvest,
        harvest_end_date=harvest_end,
        stage=stage,
        next_task=next_task,
        tasks=upcoming,
    )
