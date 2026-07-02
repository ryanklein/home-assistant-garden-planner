# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for model serialization round-trips."""

from __future__ import annotations

from datetime import date

from custom_components.garden_planner.models import (
    ActionLogEntry,
    Bed,
    Planting,
    PlantProfile,
)


def test_plant_profile_roundtrip_ignores_unknown_keys():
    profile = PlantProfile(common_name="Basil", source="bundled", source_id="basil")
    restored = PlantProfile.from_dict({**profile.to_dict(), "unexpected": 1})
    assert restored == profile


def test_planting_roundtrip_preserves_actions_and_overrides():
    planting = Planting(
        id="p1",
        bed_id="b1",
        profile=PlantProfile(common_name="Kale", source="bundled", source_id="kale"),
        manual_overrides={"sow": "2026-03-01"},
        action_log=[ActionLogEntry(kind="water", on=date(2026, 6, 1))],
    )
    restored = Planting.from_dict(planting.to_dict())
    assert restored.manual_overrides == {"sow": "2026-03-01"}
    assert restored.action_log[0].kind == "water"
    assert restored.action_log[0].on == date(2026, 6, 1)
    assert restored.last_action("water") == date(2026, 6, 1)


def test_bed_roundtrip():
    bed = Bed(
        id="b1",
        name="Raised Bed 1",
        bed_type="raised",
        sun_exposure="full",
        length_ft=8.0,
        width_ft=4.0,
        soil="loam",
    )
    restored = Bed.from_dict(bed.to_dict())
    assert restored == bed
    assert restored.length_ft == 8.0
    assert restored.width_ft == 4.0
    assert restored.bed_type == "raised"
    assert restored.soil == "loam"


def test_bed_defaults_and_legacy_keys_ignored():
    # Missing new fields default sensibly; removed keys (size/orientation) are
    # ignored rather than raising.
    bed = Bed.from_dict(
        {"id": "b2", "name": "Old Bed", "size": "8x4", "orientation": "S"}
    )
    assert bed.bed_type == "raised"
    assert bed.length_ft is None
    assert not hasattr(bed, "size")
