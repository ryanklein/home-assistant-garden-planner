# SPDX-License-Identifier: AGPL-3.0-only
"""Frost-date estimation for the Garden Planner.

Home Assistant knows the installation's latitude, from which we can approximate
the average last-spring and first-fall frost dates using a bundled climate-normal
model (frost timing correlates strongly with latitude in temperate zones). The
gardener can override either date; overrides are stored as an ISO date whose
month/day is reapplied to whichever season year we are resolving.

The estimate is intentionally coarse -- it exists so the integration is useful
out of the box. Users in microclimates should set their known local dates.
"""

from __future__ import annotations

from datetime import date, timedelta

from .schedule import FrostDates

# Anchor points: |latitude| -> (last spring frost day-of-year, first fall frost
# day-of-year) for the Northern Hemisphere. Interpolated linearly between points.
_ANCHORS: list[tuple[float, int, int]] = [
    (25.0, 15, 354),
    (30.0, 51, 339),
    (35.0, 84, 314),
    (40.0, 110, 293),
    (45.0, 130, 274),
    (50.0, 145, 263),
    (55.0, 156, 253),
    (60.0, 166, 244),
]

# Below this latitude we treat the location as effectively frost-free.
_FROST_FREE_LAT = 24.0
# Above this, extremely short season; clamp to the last anchor.
_MAX_LAT = 60.0

# Southern-hemisphere seasons are offset ~half a year from the northern model.
_SH_SHIFT_DAYS = 183


def _interpolate(abs_lat: float) -> tuple[int, int]:
    """Interpolate (last_doy, first_doy) for a Northern-Hemisphere latitude."""
    if abs_lat <= _ANCHORS[0][0]:
        return _ANCHORS[0][1], _ANCHORS[0][2]
    if abs_lat >= _ANCHORS[-1][0]:
        return _ANCHORS[-1][1], _ANCHORS[-1][2]
    for (lat_a, last_a, first_a), (lat_b, last_b, first_b) in zip(
        _ANCHORS, _ANCHORS[1:]
    ):
        if lat_a <= abs_lat <= lat_b:
            frac = (abs_lat - lat_a) / (lat_b - lat_a)
            last = round(last_a + frac * (last_b - last_a))
            first = round(first_a + frac * (first_b - first_a))
            return last, first
    return _ANCHORS[-1][1], _ANCHORS[-1][2]


def _doy_to_date(year: int, doy: int) -> date:
    """Convert a 1-based day-of-year to a concrete date, clamped to the year."""
    doy = max(1, min(doy, 365))
    return date(year, 1, 1) + timedelta(days=doy - 1)


def estimate_frost_dates(latitude: float, year: int) -> FrostDates:
    """Estimate frost dates for ``year`` from ``latitude`` alone."""
    abs_lat = abs(latitude)
    if abs_lat < _FROST_FREE_LAT:
        # Frost-free / tropical: a full-year growing window.
        return FrostDates(date(year, 1, 1), date(year, 12, 31))

    last_doy, first_doy = _interpolate(abs_lat)

    if latitude < 0:
        # Southern hemisphere: shift by half a year so the "last spring frost"
        # lands in austral spring (Sep-Nov) and the "first fall frost" in austral
        # autumn (Mar-May).
        last_doy = (last_doy + _SH_SHIFT_DAYS) % 365 or 365
        first_doy = (first_doy - _SH_SHIFT_DAYS) % 365 or 365

    return FrostDates(_doy_to_date(year, last_doy), _doy_to_date(year, first_doy))


def _apply_override(override: date | None, year: int) -> date | None:
    """Reapply an override's month/day to the requested season year."""
    if override is None:
        return None
    try:
        return override.replace(year=year)
    except ValueError:  # Feb 29 on a non-leap year
        return override.replace(year=year, day=28)


def resolve_frost_dates(
    latitude: float,
    year: int,
    last_override: date | None = None,
    first_override: date | None = None,
) -> FrostDates:
    """Frost dates for ``year``: estimate, then layer any manual overrides."""
    estimated = estimate_frost_dates(latitude, year)
    return FrostDates(
        last_frost=_apply_override(last_override, year) or estimated.last_frost,
        first_frost=_apply_override(first_override, year) or estimated.first_frost,
    )
