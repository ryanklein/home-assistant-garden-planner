# SPDX-License-Identifier: AGPL-3.0-only
"""The Garden Planner integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import GardenCoordinator
from .services import async_setup_services, async_unload_services
from .store import GardenStore

type GardenConfigEntry = ConfigEntry[RuntimeData]

_LOGGER = logging.getLogger(__name__)

# Bump to invalidate the browser cache when the card changes.
_CARD_VERSION = "0.2.0"
_CARD_URL_BASE = "/garden_planner_frontend"
_CARD_MODULE_URL = f"{_CARD_URL_BASE}/garden-planner-card.js"
_FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"


@dataclass
class RuntimeData:
    """Objects shared with platforms via ``entry.runtime_data``."""

    coordinator: GardenCoordinator
    store: GardenStore


async def async_setup_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> bool:
    """Set up Garden Planner from a config entry."""
    store = GardenStore(hass)
    await store.async_load()

    coordinator = GardenCoordinator(hass, entry, store)
    entry.runtime_data = RuntimeData(coordinator=coordinator, store=store)
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    async_setup_services(hass)
    await _async_register_frontend(hass)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the Lovelace card and auto-load it, once per HA run."""
    if hass.data.get(_FRONTEND_REGISTERED):
        return
    hass.data[_FRONTEND_REGISTERED] = True

    frontend_dir = Path(__file__).parent / "frontend"
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_CARD_URL_BASE, str(frontend_dir), cache_headers=False)]
        )
        # `frontend` is a core component and is always loaded in a real HA
        # instance; guard the runtime dependency so setup never hard-fails.
        if "frontend" in hass.config.components:
            frontend.add_extra_js_url(hass, f"{_CARD_MODULE_URL}?v={_CARD_VERSION}")
    except (RuntimeError, KeyError, ValueError) as err:  # pragma: no cover
        # Never let a card-serving hiccup prevent the integration from loading.
        hass.data[_FRONTEND_REGISTERED] = False
        _LOGGER.warning("Garden Planner card could not be registered: %s", err)


async def async_unload_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_unload_services(hass)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> None:
    """Reload when options or subentries change (adds/removes entities)."""
    await hass.config_entries.async_reload(entry.entry_id)
