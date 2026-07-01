"""Perenual (perenual.com) plant-data provider.

Perenual has strong care data (sunlight, watering, cycle, hardiness) but does not
expose precise sow/transplant/harvest timing, so those fields are left unset and
the scheduler falls back to frost-relative defaults. Requires a free API key.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import PROVIDER_PERENUAL
from ..models import PlantProfile
from . import (
    PlantDataProvider,
    PlantProviderError,
    normalize_sun,
    normalize_water,
)

_BASE = "https://perenual.com/api"
_TIMEOUT = 15


class PerenualProvider(PlantDataProvider):
    """Fetches profiles from the Perenual species API."""

    name = PROVIDER_PERENUAL

    def __init__(self, hass: HomeAssistant, api_key: str | None) -> None:
        self._hass = hass
        self._api_key = api_key

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        if not self._api_key:
            raise PlantProviderError("Perenual requires an API key")
        session = async_get_clientsession(self._hass)
        params = {**params, "key": self._api_key}
        try:
            async with asyncio.timeout(_TIMEOUT):
                resp = await session.get(f"{_BASE}/{path}", params=params)
                if resp.status == 401:
                    raise PlantProviderError("Invalid Perenual API key")
                if resp.status == 429:
                    raise PlantProviderError("Perenual rate limit reached")
                resp.raise_for_status()
                return await resp.json()
        except TimeoutError as err:
            raise PlantProviderError("Perenual request timed out") from err
        except aiohttp.ClientError as err:
            raise PlantProviderError(f"Perenual request failed: {err}") from err

    def _to_profile(self, raw: dict[str, Any]) -> PlantProfile:
        names = raw.get("scientific_name")
        scientific = names[0] if isinstance(names, list) and names else names
        return PlantProfile(
            common_name=raw.get("common_name") or "Unknown plant",
            source=self.name,
            source_id=str(raw.get("id")),
            scientific_name=scientific,
            sun=normalize_sun(raw.get("sunlight")),
            water=normalize_water(raw.get("watering")),
            notes=(raw.get("description") or None),
        )

    async def async_search(self, query: str) -> list[PlantProfile]:
        data = await self._get("species-list", {"q": query})
        return [self._to_profile(item) for item in data.get("data", [])]

    async def async_get(self, source_id: str) -> PlantProfile | None:
        data = await self._get(f"species/details/{source_id}", {})
        if not data or "id" not in data:
            return None
        return self._to_profile(data)
