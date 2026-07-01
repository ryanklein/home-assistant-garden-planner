# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the frost-relative scheduling logic (pure logic)."""

from __future__ import annotations

from datetime import date, timedelta

from custom_components.garden_planner.models import (
    ActionLogEntry,
    Planting,
    PlantProfile,
    Stage,
)
from custom_components.garden_planner.schedule import (
    FrostDates,
    compute_schedule,
)

FROST = FrostDates(last_frost=date(2026, 5, 1), first_frost=date(2026, 10, 1))


def _transplant_tomato() -> PlantProfile:
    return PlantProfile(
        common_name="Tomato",
        source="bundled",
        source_id="tomato",
        method="transplant",
        days_to_maturity=65,
        sow_weeks_before_last_frost=6,
        transplant_weeks_after_last_frost=2,
        water="medium",
    )


def _direct_radish() -> PlantProfile:
    return PlantProfile(
        common_name="Radish",
        source="bundled",
        source_id="radish",
        method="direct",
        days_to_maturity=28,
        sow_weeks_before_last_frost=4,
        water="medium",
    )


def test_transplant_dates_are_frost_relative():
    planting = Planting(id="p1", bed_id="b1", profile=_transplant_tomato(), method="transplant")
    result = compute_schedule(planting, FROST, today=date(2026, 1, 1))

    assert result.sow_date == FROST.last_frost - timedelta(weeks=6)
    assert result.transplant_date == FROST.last_frost + timedelta(weeks=2)
    # Harvest is counted from transplant for transplant crops.
    assert result.first_harvest_date == result.transplant_date + timedelta(days=65)


def test_direct_harvest_counted_from_sow():
    planting = Planting(id="p2", bed_id="b1", profile=_direct_radish(), method="direct")
    result = compute_schedule(planting, FROST, today=date(2026, 1, 1))

    assert result.sow_date == FROST.last_frost - timedelta(weeks=4)
    assert result.transplant_date is None
    assert result.first_harvest_date == result.sow_date + timedelta(days=28)


def test_manual_override_wins():
    planting = Planting(
        id="p3",
        bed_id="b1",
        profile=_direct_radish(),
        method="direct",
        manual_overrides={"sow": "2026-03-15"},
    )
    result = compute_schedule(planting, FROST, today=date(2026, 1, 1))
    assert result.sow_date == date(2026, 3, 15)


def test_stage_progression():
    profile = _direct_radish()
    planting = Planting(id="p4", bed_id="b1", profile=profile, method="direct")
    sow = FROST.last_frost - timedelta(weeks=4)

    before = compute_schedule(planting, FROST, today=sow - timedelta(days=1))
    assert before.stage is Stage.PLANNED

    just_sown = compute_schedule(planting, FROST, today=sow + timedelta(days=1))
    assert just_sown.stage is Stage.SOWN

    harvest = compute_schedule(planting, FROST, today=sow + timedelta(days=28))
    assert harvest.stage is Stage.HARVESTING


def test_next_task_is_soonest_future():
    planting = Planting(id="p5", bed_id="b1", profile=_direct_radish(), method="direct")
    # Well before sowing, the next task should be to sow.
    result = compute_schedule(planting, FROST, today=date(2026, 1, 1))
    assert result.next_task is not None
    assert result.next_task.kind == "sow"


def _overwinter_garlic() -> PlantProfile:
    return PlantProfile(
        common_name="Garlic",
        source="bundled",
        source_id="garlic",
        method="direct",
        sow_anchor="fall",
        overwinter=True,
        days_to_maturity=245,
        sow_weeks_before_last_frost=3,
        water="low",
    )


def test_overwinter_crop_sows_in_fall_and_harvests_next_year():
    planting = Planting(id="g1", bed_id="b1", profile=_overwinter_garlic(), method="direct")
    result = compute_schedule(planting, FROST, today=date(2026, 6, 1))

    # Sown relative to the first FALL frost, not the spring frost.
    assert result.sow_date == FROST.first_frost - timedelta(weeks=3)
    # Harvest lands the following year.
    assert result.first_harvest_date.year == FROST.first_frost.year + 1
    assert result.season_label == "2026–2027"


def test_overwinter_crop_has_no_water_tasks():
    planting = Planting(id="g2", bed_id="b1", profile=_overwinter_garlic(), method="direct")
    # A date after sowing when a normal crop would have watering due.
    result = compute_schedule(planting, FROST, today=date(2026, 10, 1))
    assert all(t.kind != "water" for t in result.tasks)


def test_spring_crop_season_label_is_single_year():
    planting = Planting(id="r1", bed_id="b1", profile=_direct_radish(), method="direct")
    result = compute_schedule(planting, FROST, today=date(2026, 1, 1))
    assert result.season_label == "2026"


def test_logged_action_removes_sow_task_and_advances():
    profile = _direct_radish()
    sow = FROST.last_frost - timedelta(weeks=4)
    planting = Planting(
        id="p6",
        bed_id="b1",
        profile=profile,
        method="direct",
        action_log=[ActionLogEntry(kind="sow", on=sow)],
    )
    result = compute_schedule(planting, FROST, today=sow + timedelta(days=2))
    kinds = {t.kind for t in result.tasks}
    assert "sow" not in kinds
