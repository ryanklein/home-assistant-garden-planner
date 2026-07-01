"""The Garden Planner integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import GardenCoordinator
from .services import async_setup_services, async_unload_services
from .store import GardenStore

type GardenConfigEntry = ConfigEntry[RuntimeData]


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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_unload_services(hass)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: GardenConfigEntry) -> None:
    """Reload when options or subentries change (adds/removes entities)."""
    await hass.config_entries.async_reload(entry.entry_id)
