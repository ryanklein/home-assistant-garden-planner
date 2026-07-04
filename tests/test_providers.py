# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for plant-data provider normalization."""

from __future__ import annotations

from custom_components.garden_planner.providers.permapeople import (
    PermaPeopleProvider,
)


def test_permapeople_normalizes_plant():
    provider = PermaPeopleProvider(None, "key-id", "key-secret")
    raw = {
        "id": 101,
        "name": "White mulberry",
        "scientific_name": "Morus alba",
        "description": "Young leaves are edible.",
        "data": [
            {"key": "Light requirement", "value": "Full sun, partial sun/shade"},
            {"key": "Water requirement", "value": "Moist"},
            {"key": "Layer", "value": "Trees"},
        ],
    }
    profile = provider._to_profile(raw)
    assert profile.common_name == "White mulberry"
    assert profile.scientific_name == "Morus alba"
    assert profile.source == "permapeople"
    assert profile.source_id == "101"
    assert profile.sun == "full"  # first of the comma-separated light values
    assert profile.water == "medium"  # "Moist" -> medium
    assert profile.notes == "Young leaves are edible."
