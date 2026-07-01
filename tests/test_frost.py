# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the frost-date estimation model (pure logic)."""

from __future__ import annotations

from datetime import date

from custom_components.garden_planner.frost import (
    estimate_frost_dates,
    resolve_frost_dates,
)


def test_northern_hemisphere_ordering():
    """Last spring frost comes before first fall frost up north."""
    frost = estimate_frost_dates(latitude=42.0, year=2026)
    assert frost.last_frost < frost.first_frost
    assert frost.last_frost.year == 2026
    assert frost.first_frost.year == 2026


def test_higher_latitude_has_shorter_season():
    """Colder (higher-latitude) locations get a later, shorter window."""
    warm = estimate_frost_dates(latitude=32.0, year=2026)
    cold = estimate_frost_dates(latitude=48.0, year=2026)
    warm_season = (warm.first_frost - warm.last_frost).days
    cold_season = (cold.first_frost - cold.last_frost).days
    assert cold.last_frost > warm.last_frost
    assert cold_season < warm_season


def test_tropical_is_frost_free():
    """Near the equator we return a full-year growing window."""
    frost = estimate_frost_dates(latitude=10.0, year=2026)
    assert frost.last_frost == date(2026, 1, 1)
    assert frost.first_frost == date(2026, 12, 31)


def test_southern_hemisphere_shifts_seasons():
    """Southern-hemisphere last frost lands in the second half of the year."""
    frost = estimate_frost_dates(latitude=-37.0, year=2026)
    assert frost.last_frost.month >= 8  # austral spring
    assert frost.first_frost.month <= 6  # austral autumn


def test_manual_override_wins_and_reyears():
    """An override's month/day is reapplied to the requested season year."""
    frost = resolve_frost_dates(
        latitude=42.0,
        year=2026,
        last_override=date(2020, 5, 1),
        first_override=None,
    )
    assert frost.last_frost == date(2026, 5, 1)
    # First frost still comes from the estimate.
    assert frost.first_frost.year == 2026
