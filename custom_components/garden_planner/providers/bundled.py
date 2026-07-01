# SPDX-License-Identifier: AGPL-3.0-only
"""Offline plant-data provider backed by the bundled ``data/plants.json``.

This provider has no external dependencies, so the integration is fully usable
with no API key or network access. It also serves as the automatic fallback when
an online provider is unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import PROVIDER_BUNDLED
from ..models import PlantProfile
from . import PlantDataProvider

_DATA_FILE = Path(__file__).parent.parent / "data" / "plants.json"


class BundledProvider(PlantDataProvider):
    """Serves profiles from the packaged crop dataset."""

    name = PROVIDER_BUNDLED

    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self._data = data

    @classmethod
    async def async_create(cls, hass: HomeAssistant) -> BundledProvider:
        """Load the dataset off the event loop."""
        data = await hass.async_add_executor_job(cls._load)
        return cls(data)

    @staticmethod
    def _load() -> dict[str, dict[str, Any]]:
        with _DATA_FILE.open(encoding="utf-8") as file:
            return json.load(file)

    def _to_profile(self, key: str, raw: dict[str, Any]) -> PlantProfile:
        return PlantProfile.from_dict(
            {**raw, "source": self.name, "source_id": key}
        )

    async def async_search(self, query: str) -> list[PlantProfile]:
        query = (query or "").strip().lower()
        results: list[PlantProfile] = []
        for key, raw in self._data.items():
            haystack = f"{key} {raw.get('common_name', '')}".lower()
            if not query or query in haystack:
                results.append(self._to_profile(key, raw))
        results.sort(key=lambda p: p.common_name)
        return results

    async def async_get(self, source_id: str) -> PlantProfile | None:
        raw = self._data.get(source_id)
        return self._to_profile(source_id, raw) if raw else None
