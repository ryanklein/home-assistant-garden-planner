# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for setup, config flow and the bundled provider (HA harness)."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_planner.const import (
    CONF_PROVIDER,
    DEFAULT_PROVIDER,
    DOMAIN,
)
from custom_components.garden_planner.providers.bundled import BundledProvider


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The user step creates the single garden entry with default options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_PROVIDER] == DEFAULT_PROVIDER


async def test_single_instance_only(hass: HomeAssistant) -> None:
    """A second setup attempt is aborted."""
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_setup_entry_loads(hass: HomeAssistant) -> None:
    """The integration sets up and registers its services."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        options={CONF_PROVIDER: DEFAULT_PROVIDER},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "log_action")
    assert entry.runtime_data.coordinator.data is not None


async def test_bundled_provider_search_and_get(hass: HomeAssistant) -> None:
    """The offline provider loads the packaged dataset."""
    provider = await BundledProvider.async_create(hass)

    matches = await provider.async_search("tomato")
    assert any(p.common_name == "Tomato" for p in matches)

    profile = await provider.async_get("tomato")
    assert profile is not None
    assert profile.method == "transplant"
    assert profile.source == DEFAULT_PROVIDER
