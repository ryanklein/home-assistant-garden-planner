# SPDX-License-Identifier: AGPL-3.0-only
"""OpenFarm (openfarm.cc) plant-data provider.

OpenFarm is a community crop database oriented toward growing information (sun
requirements, sowing method, spacing). It needs no API key. Data completeness and
uptime vary, so unset fields simply fall back to scheduler defaults.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import METHOD_DIRECT, METHOD_TRANSPLANT, PROVIDER_OPENFARM
from ..models import PlantProfile
from . import PlantDataProvider, PlantProviderError, normalize_sun

_BASE = "https://openfarm.cc/api/v1"
_TIMEOUT = 15


class OpenFarmProvider(PlantDataProvider):
    """Fetches profiles from the OpenFarm crops API."""

    name = PROVIDER_OPENFARM

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        session = async_get_clientsession(self._hass)
        try:
            async with asyncio.timeout(_TIMEOUT):
                resp = await session.get(f"{_BASE}/{path}", params=params)
                resp.raise_for_status()
                return await resp.json()
        except TimeoutError as err:
            raise PlantProviderError("OpenFarm request timed out") from err
        except aiohttp.ClientError as err:
            raise PlantProviderError(f"OpenFarm request failed: {err}") from err

    def _to_profile(self, item: dict[str, Any]) -> PlantProfile:
        attrs = item.get("attributes", {})
        sowing = (attrs.get("sowing_method") or "").lower()
        method = METHOD_TRANSPLANT if "transplant" in sowing else METHOD_DIRECT
        spacing = attrs.get("row_spacing") or attrs.get("spread")
        return PlantProfile(
            common_name=attrs.get("name") or "Unknown plant",
            source=self.name,
            source_id=str(item.get("id")),
            scientific_name=attrs.get("binomial_name") or None,
            sun=normalize_sun(attrs.get("sun_requirements")),
            days_to_maturity=attrs.get("growing_degree_days") or None,
            method=method,
            spacing_cm=float(spacing) if spacing else None,
            notes=(attrs.get("description") or None),
        )

    async def async_search(self, query: str) -> list[PlantProfile]:
        data = await self._get("crops", {"filter": query})
        return [self._to_profile(item) for item in data.get("data", [])]

    async def async_get(self, source_id: str) -> PlantProfile | None:
        data = await self._get(f"crops/{source_id}", {})
        item = data.get("data")
        return self._to_profile(item) if item else None
