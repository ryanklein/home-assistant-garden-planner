# SPDX-License-Identifier: AGPL-3.0-only
"""PermaPeople (permapeople.org) plant-data provider.

PermaPeople is a community, permaculture-oriented plant database. Care data comes
as flexible key/value pairs (light/water requirement, layer, hardiness zone, ...);
it does not expose precise sow/transplant/harvest timing, so those fields are left
unset and the scheduler falls back to frost-relative defaults.

Authentication uses a key id + key secret (create them in your PermaPeople
account settings), sent as request headers.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import PROVIDER_PERMAPEOPLE
from ..models import PlantProfile
from . import (
    PlantDataProvider,
    PlantProviderError,
    normalize_sun,
    normalize_water,
)

_BASE = "https://permapeople.org/api"
_TIMEOUT = 15


def _first(value: str | None) -> str | None:
    """PermaPeople multi-values are comma-separated; take the first."""
    if not value:
        return None
    return value.split(",")[0].strip()


class PermaPeopleProvider(PlantDataProvider):
    """Fetches profiles from the PermaPeople API."""

    name = PROVIDER_PERMAPEOPLE

    def __init__(
        self, hass: HomeAssistant, key_id: str | None, key_secret: str | None
    ) -> None:
        self._hass = hass
        self._key_id = key_id
        self._key_secret = key_secret

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._key_id or not self._key_secret:
            raise PlantProviderError("PermaPeople requires a key id and secret")
        session = async_get_clientsession(self._hass)
        headers = {
            "x-permapeople-key-id": self._key_id,
            "x-permapeople-key-secret": self._key_secret,
        }
        try:
            async with asyncio.timeout(_TIMEOUT):
                resp = await session.get(
                    f"{_BASE}/{path}", headers=headers, params=params
                )
                if resp.status == 401:
                    raise PlantProviderError("Invalid PermaPeople credentials")
                if resp.status == 429:
                    raise PlantProviderError("PermaPeople rate limit reached")
                resp.raise_for_status()
                return await resp.json()
        except TimeoutError as err:
            raise PlantProviderError("PermaPeople request timed out") from err
        except aiohttp.ClientError as err:
            raise PlantProviderError(f"PermaPeople request failed: {err}") from err

    def _to_profile(self, raw: dict[str, Any]) -> PlantProfile:
        # Flatten the key/value `data` list into a dict for easy lookup.
        data = {
            item.get("key"): item.get("value")
            for item in raw.get("data", [])
            if isinstance(item, dict)
        }
        return PlantProfile(
            common_name=raw.get("name") or "Unknown plant",
            source=self.name,
            source_id=str(raw.get("id")),
            scientific_name=raw.get("scientific_name") or None,
            sun=normalize_sun(_first(data.get("Light requirement"))),
            water=normalize_water(_first(data.get("Water requirement"))),
            notes=(raw.get("description") or None),
        )

    async def async_search(self, query: str) -> list[PlantProfile]:
        data = await self._request("search", params={"q": query})
        return [self._to_profile(item) for item in data.get("plants", [])]

    async def async_get(self, source_id: str) -> PlantProfile | None:
        data = await self._request(f"plants/{source_id}")
        if not data or "id" not in data:
            return None
        return self._to_profile(data)
