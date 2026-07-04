# SPDX-License-Identifier: AGPL-3.0-only
"""Pluggable plant-data providers.

A provider turns a free-text query or a source id into one or more normalized
:class:`~custom_components.garden_planner.models.PlantProfile` objects. The rest
of the integration only ever sees the normalized shape, so sources can be swapped
or fall back to one another without touching scheduling or entity code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from homeassistant.core import HomeAssistant

from ..const import (
    PROVIDER_BUNDLED,
    PROVIDER_OPENFARM,
    PROVIDER_PERMAPEOPLE,
    SUN_FULL,
    SUN_PARTIAL,
    SUN_SHADE,
    WATER_HIGH,
    WATER_LOW,
    WATER_MEDIUM,
)
from ..models import PlantProfile


class PlantProviderError(Exception):
    """Raised when a provider cannot fulfil a request."""


class PlantDataProvider(ABC):
    """Base class for a plant-data source."""

    name: str

    @abstractmethod
    async def async_search(self, query: str) -> list[PlantProfile]:
        """Return candidate profiles matching a free-text query."""

    @abstractmethod
    async def async_get(self, source_id: str) -> PlantProfile | None:
        """Return a single profile by its source-specific id."""


# --- Normalization helpers shared by providers -----------------------------

_SUN_MAP = {
    "full": SUN_FULL,
    "full_sun": SUN_FULL,
    "full sun": SUN_FULL,
    "sun": SUN_FULL,
    "part_sun": SUN_PARTIAL,
    "part_shade": SUN_PARTIAL,
    "part sun/part shade": SUN_PARTIAL,
    "partial": SUN_PARTIAL,
    "partial shade": SUN_PARTIAL,
    "partial sun": SUN_PARTIAL,
    "partial sun/shade": SUN_PARTIAL,
    "filtered shade": SUN_PARTIAL,
    "shade": SUN_SHADE,
    "full_shade": SUN_SHADE,
    "full shade": SUN_SHADE,
    "deep shade": SUN_SHADE,
}

_WATER_MAP = {
    "frequent": WATER_HIGH,
    "high": WATER_HIGH,
    "average": WATER_MEDIUM,
    "medium": WATER_MEDIUM,
    "moderate": WATER_MEDIUM,
    "minimum": WATER_LOW,
    "minimal": WATER_LOW,
    "low": WATER_LOW,
    "none": WATER_LOW,
    # PermaPeople "Water requirement" values.
    "dry": WATER_LOW,
    "moist": WATER_MEDIUM,
    "wet": WATER_HIGH,
    "aquatic": WATER_HIGH,
}


def normalize_sun(value: str | list | None, default: str = SUN_FULL) -> str:
    """Map an arbitrary provider sun value onto our sun enum."""
    if isinstance(value, list):
        value = value[0] if value else None
    if not value:
        return default
    return _SUN_MAP.get(str(value).strip().lower(), default)


def normalize_water(value: str | None, default: str = WATER_MEDIUM) -> str:
    """Map an arbitrary provider watering value onto our water enum."""
    if not value:
        return default
    return _WATER_MAP.get(str(value).strip().lower(), default)


async def async_get_provider(
    hass: HomeAssistant,
    provider: str,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> PlantDataProvider:
    """Instantiate a provider by name (imports are local to keep setup cheap)."""
    if provider == PROVIDER_PERMAPEOPLE:
        from .permapeople import PermaPeopleProvider

        return PermaPeopleProvider(hass, api_key, api_secret)
    if provider == PROVIDER_OPENFARM:
        from .openfarm import OpenFarmProvider

        return OpenFarmProvider(hass)
    # Default / fallback.
    from .bundled import BundledProvider

    return await BundledProvider.async_create(hass)
