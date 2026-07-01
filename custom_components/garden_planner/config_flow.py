"""Config, options and subentry flows for Garden Planner."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_BED_ID,
    CONF_FIRST_FROST,
    CONF_LAST_FROST,
    CONF_METHOD,
    CONF_NAME,
    CONF_NOTES,
    CONF_ORIENTATION,
    CONF_PLANT_QUERY,
    CONF_PLANT_SOURCE_ID,
    CONF_PROVIDER,
    CONF_QUANTITY,
    CONF_SEASON_YEAR,
    CONF_SIZE,
    CONF_SOIL,
    CONF_SUN_EXPOSURE,
    CONF_UNITS,
    DEFAULT_PROVIDER,
    DEFAULT_UNITS,
    DOMAIN,
    METHOD_VALUES,
    PROVIDER_PERENUAL,
    PROVIDERS,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
    SUN_VALUES,
    UNITS_IMPERIAL,
    UNITS_METRIC,
)
from .models import PlantProfile
from .providers import PlantProviderError, async_get_provider


def _select(options: list[str], key: str) -> selector.SelectSelector:
    """A translated dropdown selector for a fixed option list."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=key,
        )
    )


class GardenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of the garden."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single garden config entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title="Garden Planner",
                data={},
                options={
                    CONF_PROVIDER: DEFAULT_PROVIDER,
                    CONF_UNITS: DEFAULT_UNITS,
                },
            )
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GardenOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_TYPE_BED: BedSubentryFlow,
            SUBENTRY_TYPE_PLANTING: PlantingSubentryFlow,
        }


class GardenOptionsFlow(OptionsFlow):
    """Global garden settings: provider, API key, units, frost overrides."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # Drop empty optional values so estimates are used again.
            cleaned = {k: v for k, v in user_input.items() if v not in (None, "")}
            return self.async_create_entry(data=cleaned)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PROVIDER,
                    default=current.get(CONF_PROVIDER, DEFAULT_PROVIDER),
                ): _select(PROVIDERS, "provider"),
                vol.Optional(
                    CONF_API_KEY,
                    description={"suggested_value": current.get(CONF_API_KEY)},
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Required(
                    CONF_UNITS, default=current.get(CONF_UNITS, DEFAULT_UNITS)
                ): _select([UNITS_METRIC, UNITS_IMPERIAL], "units"),
                vol.Optional(
                    CONF_LAST_FROST,
                    description={"suggested_value": current.get(CONF_LAST_FROST)},
                ): selector.DateSelector(),
                vol.Optional(
                    CONF_FIRST_FROST,
                    description={"suggested_value": current.get(CONF_FIRST_FROST)},
                ): selector.DateSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class BedSubentryFlow(ConfigSubentryFlow):
    """Add or reconfigure a garden bed."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input
            )
        return self.async_show_form(
            step_id="user", data_schema=self._schema()
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_NAME],
                data=user_input,
            )
        return self.async_show_form(
            step_id="reconfigure", data_schema=self._schema(subentry.data)
        )

    def _schema(self, defaults: dict[str, Any] | None = None) -> vol.Schema:
        defaults = defaults or {}
        return vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=defaults.get(CONF_NAME, "")
                ): str,
                vol.Required(
                    CONF_SUN_EXPOSURE,
                    default=defaults.get(CONF_SUN_EXPOSURE, SUN_VALUES[0]),
                ): _select(SUN_VALUES, "sun_exposure"),
                vol.Optional(
                    CONF_SIZE,
                    description={"suggested_value": defaults.get(CONF_SIZE)},
                ): str,
                vol.Optional(
                    CONF_ORIENTATION,
                    description={"suggested_value": defaults.get(CONF_ORIENTATION)},
                ): str,
                vol.Optional(
                    CONF_SOIL,
                    description={"suggested_value": defaults.get(CONF_SOIL)},
                ): str,
                vol.Optional(
                    CONF_NOTES,
                    description={"suggested_value": defaults.get(CONF_NOTES)},
                ): str,
            }
        )


class PlantingSubentryFlow(ConfigSubentryFlow):
    """Add a planting: pick a bed, search for a plant, choose a match."""

    def __init__(self) -> None:
        self._matches: dict[str, PlantProfile] = {}
        self._pending: dict[str, Any] = {}

    def _beds(self) -> dict[str, str]:
        entry = self._get_entry()
        return {
            sub.subentry_id: sub.title
            for sub in entry.subentries.values()
            if sub.subentry_type == SUBENTRY_TYPE_BED
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        beds = self._beds()
        if not beds:
            return self.async_abort(reason="no_beds")

        if user_input is not None:
            self._pending = user_input
            return await self.async_step_pick()

        this_year = datetime.now().year
        schema = vol.Schema(
            {
                vol.Required(CONF_BED_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=bid, label=name)
                            for bid, name in beds.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_PLANT_QUERY): str,
                vol.Optional(CONF_METHOD): _select(METHOD_VALUES, "method"),
                vol.Required(CONF_QUANTITY, default=1): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=999, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_SEASON_YEAR, default=this_year
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=this_year - 1,
                        max=this_year + 5,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show plant matches for the query and let the user choose one."""
        if user_input is not None:
            profile = self._matches[user_input[CONF_PLANT_SOURCE_ID]]
            return await self._create(profile)

        provider, note = await self._resolve_provider()
        try:
            results = await provider.async_search(self._pending[CONF_PLANT_QUERY])
        except PlantProviderError:
            results = []

        if not results:
            return self.async_abort(reason="no_matches")

        self._matches = {p.source_id: p for p in results}
        options = [
            selector.SelectOptionDict(
                value=p.source_id,
                label=f"{p.common_name}"
                + (f" ({p.scientific_name})" if p.scientific_name else ""),
            )
            for p in results
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_PLANT_SOURCE_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="pick",
            data_schema=schema,
            description_placeholders={"note": note},
        )

    async def _resolve_provider(self) -> tuple[Any, str]:
        """Return the configured provider, falling back to bundled on error."""
        options = self._get_entry().options
        name = options.get(CONF_PROVIDER, DEFAULT_PROVIDER)
        api_key = options.get(CONF_API_KEY)
        if name == PROVIDER_PERENUAL and not api_key:
            provider = await async_get_provider(self.hass, DEFAULT_PROVIDER)
            return provider, "No API key set; showing bundled plants."
        provider = await async_get_provider(self.hass, name, api_key)
        return provider, ""

    async def _create(self, profile: PlantProfile) -> SubentryFlowResult:
        entry = self._get_entry()
        # Cache the chosen profile so the planting survives provider outages.
        if (runtime := getattr(entry, "runtime_data", None)) is not None:
            await runtime.store.async_cache_profile(profile)

        method = self._pending.get(CONF_METHOD) or profile.method
        data = {
            CONF_BED_ID: self._pending[CONF_BED_ID],
            "profile": profile.to_dict(),
            "method": method,
            "quantity": int(self._pending.get(CONF_QUANTITY, 1)),
            "season_year": int(self._pending[CONF_SEASON_YEAR]),
            "manual_overrides": {},
        }
        bed_name = self._beds().get(self._pending[CONF_BED_ID], "")
        title = f"{profile.common_name} — {bed_name}" if bed_name else profile.common_name
        return self.async_create_entry(title=title, data=data)
