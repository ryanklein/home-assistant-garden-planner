# SPDX-License-Identifier: AGPL-3.0-only
"""Persistent storage for Garden Planner runtime state.

Bed and planting *configuration* lives in config subentries (so it is editable
through the HA UI). This ``Store`` holds the mutable, frequently-written runtime
state that does not belong in a config entry:

* ``action_logs`` -- what the gardener actually did (watered/transplanted/...),
  keyed by planting id.
* ``profile_cache`` -- the last-known plant profile for each ``source:source_id``
  so plantings keep working when a provider is offline or a plant is removed
  upstream.
"""

from __future__ import annotations

from datetime import date

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import ActionLogEntry, PlantProfile


def _cache_key(source: str, source_id: str) -> str:
    return f"{source}:{source_id}"


class GardenStore:
    """Thin async wrapper around the HA ``Store`` for our data shapes."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict = {"action_logs": {}, "profile_cache": {}, "archive": []}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self._data = {
                "action_logs": data.get("action_logs", {}),
                "profile_cache": data.get("profile_cache", {}),
                "archive": data.get("archive", []),
            }

    async def _async_save(self) -> None:
        await self._store.async_save(self._data)

    # --- Action log ---------------------------------------------------------

    def get_actions(self, planting_id: str) -> list[ActionLogEntry]:
        raw = self._data["action_logs"].get(planting_id, [])
        return [ActionLogEntry.from_dict(item) for item in raw]

    async def async_add_action(self, planting_id: str, kind: str, on: date) -> None:
        entry = ActionLogEntry(kind=kind, on=on)
        self._data["action_logs"].setdefault(planting_id, []).append(entry.to_dict())
        await self._async_save()

    async def async_clear_planting(self, planting_id: str) -> None:
        """Drop stored state for a planting that has been removed."""
        if self._data["action_logs"].pop(planting_id, None) is not None:
            await self._async_save()

    # --- Archive / history --------------------------------------------------

    def get_archive(self) -> list[dict]:
        return list(self._data["archive"])

    async def async_archive(self, record: dict) -> None:
        """Append a season-history record and drop the live action log."""
        self._data["archive"].append(record)
        self._data["action_logs"].pop(record.get("planting_id"), None)
        await self._async_save()

    async def async_reconcile(self, valid_ids: set[str]) -> None:
        """Archive action logs whose planting no longer exists.

        Safety net so history is not silently lost when a planting is deleted
        directly from the Home Assistant UI (which we cannot intercept).
        """
        orphans = [pid for pid in self._data["action_logs"] if pid not in valid_ids]
        if not orphans:
            return
        for planting_id in orphans:
            self._data["archive"].append(
                {
                    "planting_id": planting_id,
                    "reason": "orphaned",
                    "action_log": self._data["action_logs"].pop(planting_id),
                }
            )
        await self._async_save()

    # --- Profile cache ------------------------------------------------------

    def get_cached_profile(self, source: str, source_id: str) -> PlantProfile | None:
        raw = self._data["profile_cache"].get(_cache_key(source, source_id))
        return PlantProfile.from_dict(raw) if raw else None

    async def async_cache_profile(self, profile: PlantProfile) -> None:
        self._data["profile_cache"][_cache_key(profile.source, profile.source_id)] = (
            profile.to_dict()
        )
        await self._async_save()
