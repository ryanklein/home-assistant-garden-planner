# SPDX-License-Identifier: AGPL-3.0-only
"""Config, options and subentry flows for Garden Planner."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ADD_NEW,
    BED_TYPE_VALUES,
    CONF_API_KEY,
    CONF_BED_ID,
    CONF_BED_TYPE,
    CONF_FIRST_FROST,
    CONF_LAST_FROST,
    CONF_LENGTH_FT,
    CONF_METHOD,
    CONF_NAME,
    CONF_NOTES,
    CONF_PLANT_QUERY,
    CONF_PLANT_SOURCE_ID,
    CONF_PROVIDER,
    CONF_QUANTITY,
    CONF_SEASON_YEAR,
    CONF_SEED_ID,
    CONF_SKU,
    CONF_SOIL,
    CONF_SUCCESSION_INTERVAL,
    CONF_SUCCESSIONS,
    CONF_SUN_EXPOSURE,
    CONF_UNITS,
    CONF_URL,
    CONF_VARIETY,
    CONF_VENDOR_ID,
    CONF_VENDOR_NAME,
    CONF_WIDTH_FT,
    DEFAULT_BED_TYPE,
    DEFAULT_PROVIDER,
    DEFAULT_SUCCESSION_INTERVAL_DAYS,
    DEFAULT_UNITS,
    DOMAIN,
    METHOD_VALUES,
    PROVIDER_PERENUAL,
    PROVIDERS,
    SOIL_VALUES,
    SUBENTRY_TYPE_BED,
    SUBENTRY_TYPE_PLANTING,
    SUBENTRY_TYPE_SEED,
    SUBENTRY_TYPE_VENDOR,
    SUN_VALUES,
    UNITS_IMPERIAL,
    UNITS_METRIC,
    VENDOR_UNKNOWN_ID,
    VENDOR_UNKNOWN_NAME,
)
from .frost import resolve_frost_dates
from .models import Planting, PlantProfile
from .providers import PlantProviderError, async_get_provider
from .schedule import compute_sow_date


def _parse_iso(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _select(options: list[str], key: str) -> selector.SelectSelector:
    """A translated dropdown selector for a fixed option list."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=key,
        )
    )


def _radio(options: list[str], key: str) -> selector.SelectSelector:
    """A translated radio-button selector for a fixed option list."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.LIST,
            translation_key=key,
        )
    )


def _feet() -> selector.NumberSelector:
    """A number input measured in feet."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            step=0.5,
            unit_of_measurement="ft",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


# --- Vendor / seed helpers shared by the seed and planting flows -----------


async def _resolve_provider(hass, entry: ConfigEntry) -> tuple[Any, str]:
    """Return the configured plant-data provider, falling back to bundled."""
    options = entry.options
    name = options.get(CONF_PROVIDER, DEFAULT_PROVIDER)
    api_key = options.get(CONF_API_KEY)
    if name == PROVIDER_PERENUAL and not api_key:
        provider = await async_get_provider(hass, DEFAULT_PROVIDER)
        return provider, "No API key set; showing bundled plants."
    return await async_get_provider(hass, name, api_key), ""


def _existing_vendors(entry: ConfigEntry) -> dict[str, str]:
    return {
        sub.subentry_id: sub.data.get(CONF_NAME, sub.title)
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TYPE_VENDOR
    }


def _vendor_name(entry: ConfigEntry, vendor_id: str) -> str:
    if vendor_id == VENDOR_UNKNOWN_ID:
        return VENDOR_UNKNOWN_NAME
    return _existing_vendors(entry).get(vendor_id, VENDOR_UNKNOWN_NAME)


def _vendor_select(entry: ConfigEntry) -> selector.SelectSelector:
    """Dropdown of existing vendors + 'Saved/Unknown' + 'Add new vendor'."""
    options = [
        selector.SelectOptionDict(value=VENDOR_UNKNOWN_ID, label=VENDOR_UNKNOWN_NAME)
    ]
    options += [
        selector.SelectOptionDict(value=vid, label=name)
        for vid, name in sorted(
            _existing_vendors(entry).items(), key=lambda kv: kv[1].lower()
        )
    ]
    options.append(selector.SelectOptionDict(value=ADD_NEW, label="➕ Add new vendor…"))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


def _seed_select_for_vendor(
    entry: ConfigEntry, vendor_id: str
) -> selector.SelectSelector:
    """Dropdown of a vendor's seeds + 'Add new seed'."""
    options = [
        selector.SelectOptionDict(value=sub.subentry_id, label=sub.title)
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_TYPE_SEED
        and sub.data.get(CONF_VENDOR_ID) == vendor_id
    ]
    options.append(selector.SelectOptionDict(value=ADD_NEW, label="➕ Add new seed…"))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


def _plant_label(variety: str | None, common_name: str) -> str:
    """Human label combining a variety with its species, e.g. 'Cherokee Tomato'."""
    if variety and variety.lower() not in common_name.lower():
        return f"{variety} {common_name}"
    return variety or common_name


def _seed_title(vendor_name: str, variety: str | None, common_name: str) -> str:
    label = _plant_label(variety, common_name)
    return f"{label} ({vendor_name})" if vendor_name else label


def _make_seed_data(
    vendor_id: str,
    vendor_name: str,
    variety: str,
    sku: str | None,
    url: str | None,
    profile: PlantProfile,
) -> dict[str, Any]:
    return {
        CONF_VENDOR_ID: vendor_id,
        CONF_VENDOR_NAME: vendor_name,
        CONF_VARIETY: variety,
        CONF_SKU: sku or None,
        CONF_URL: url or None,
        "profile": profile.to_dict(),
    }


def _add_vendor(hass, entry: ConfigEntry, name: str, url: str | None) -> tuple[str, str]:
    """Create a vendor subentry inline; return its (id, name)."""
    sub = ConfigSubentry(
        data={CONF_NAME: name, CONF_URL: url or None},
        subentry_type=SUBENTRY_TYPE_VENDOR,
        title=name,
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, sub)
    return sub.subentry_id, name


async def _add_seed(
    hass,
    entry: ConfigEntry,
    vendor_id: str,
    vendor_name: str,
    variety: str,
    sku: str | None,
    url: str | None,
    profile: PlantProfile,
) -> str:
    """Create a seed subentry inline; cache its profile; return its id."""
    if (runtime := getattr(entry, "runtime_data", None)) is not None:
        await runtime.store.async_cache_profile(profile)
    sub = ConfigSubentry(
        data=_make_seed_data(vendor_id, vendor_name, variety, sku, url, profile),
        subentry_type=SUBENTRY_TYPE_SEED,
        title=_seed_title(vendor_name, variety, profile.common_name),
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, sub)
    return sub.subentry_id


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
            SUBENTRY_TYPE_VENDOR: VendorSubentryFlow,
            SUBENTRY_TYPE_SEED: SeedSubentryFlow,
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
                    CONF_BED_TYPE,
                    default=defaults.get(CONF_BED_TYPE, DEFAULT_BED_TYPE),
                ): _radio(BED_TYPE_VALUES, "bed_type"),
                vol.Required(
                    CONF_SUN_EXPOSURE,
                    default=defaults.get(CONF_SUN_EXPOSURE, SUN_VALUES[0]),
                ): _select(SUN_VALUES, "sun_exposure"),
                vol.Optional(
                    CONF_LENGTH_FT,
                    description={"suggested_value": defaults.get(CONF_LENGTH_FT)},
                ): _feet(),
                vol.Optional(
                    CONF_WIDTH_FT,
                    description={"suggested_value": defaults.get(CONF_WIDTH_FT)},
                ): _feet(),
                vol.Optional(
                    CONF_SOIL,
                    description={"suggested_value": defaults.get(CONF_SOIL)},
                ): _select(SOIL_VALUES, "soil"),
                vol.Optional(
                    CONF_NOTES,
                    description={"suggested_value": defaults.get(CONF_NOTES)},
                ): str,
            }
        )


class VendorSubentryFlow(ConfigSubentryFlow):
    """Add or reconfigure a seed/plant vendor."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input
            )
        return self.async_show_form(step_id="user", data_schema=self._schema())

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
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
                vol.Optional(
                    CONF_URL,
                    description={"suggested_value": defaults.get(CONF_URL)},
                ): str,
                vol.Optional(
                    CONF_NOTES,
                    description={"suggested_value": defaults.get(CONF_NOTES)},
                ): str,
            }
        )


class SeedSubentryFlow(ConfigSubentryFlow):
    """Add a seed: pick/add a vendor, search for a plant, choose a match."""

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}
        self._vendor_id: str | None = None
        self._vendor_name: str | None = None
        self._matches: dict[str, PlantProfile] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._pending = user_input
            choice = user_input[CONF_VENDOR_ID]
            if choice == ADD_NEW:
                return await self.async_step_vendor_new()
            self._vendor_id = choice
            self._vendor_name = _vendor_name(self._get_entry(), choice)
            return await self.async_step_pick()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VENDOR_ID, default=VENDOR_UNKNOWN_ID
                ): _vendor_select(self._get_entry()),
                vol.Required(CONF_PLANT_QUERY): str,
                vol.Required(CONF_VARIETY): str,
                vol.Optional(CONF_SKU): str,
                vol.Optional(CONF_URL): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_vendor_new(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._vendor_id, self._vendor_name = _add_vendor(
                self.hass, self._get_entry(), user_input[CONF_NAME],
                user_input.get(CONF_URL),
            )
            return await self.async_step_pick()
        return self.async_show_form(
            step_id="vendor_new",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME): str, vol.Optional(CONF_URL): str}
            ),
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            profile = self._matches[user_input[CONF_PLANT_SOURCE_ID]]
            entry = self._get_entry()
            if (runtime := getattr(entry, "runtime_data", None)) is not None:
                await runtime.store.async_cache_profile(profile)
            data = _make_seed_data(
                self._vendor_id,
                self._vendor_name,
                self._pending[CONF_VARIETY],
                self._pending.get(CONF_SKU),
                self._pending.get(CONF_URL),
                profile,
            )
            title = _seed_title(
                self._vendor_name, self._pending[CONF_VARIETY], profile.common_name
            )
            return self.async_create_entry(title=title, data=data)

        schema, note = await _plant_pick_schema(
            self.hass, self._get_entry(), self._pending[CONF_PLANT_QUERY],
            self._matches,
        )
        if schema is None:
            return self.async_abort(reason="no_matches")
        return self.async_show_form(
            step_id="pick", data_schema=schema, description_placeholders={"note": note}
        )


async def _plant_pick_schema(
    hass, entry: ConfigEntry, query: str, matches: dict[str, PlantProfile]
) -> tuple[vol.Schema | None, str]:
    """Run a provider search and build the 'choose a plant' schema.

    Populates ``matches`` in place. Returns ``(None, "")`` if nothing matched.
    """
    provider, note = await _resolve_provider(hass, entry)
    try:
        results = await provider.async_search(query)
    except PlantProviderError:
        results = []
    if not results:
        return None, note

    matches.clear()
    matches.update({p.source_id: p for p in results})
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
                    options=options, mode=selector.SelectSelectorMode.LIST
                )
            )
        }
    )
    return schema, note


class PlantingSubentryFlow(ConfigSubentryFlow):
    """Add a planting in the order: vendor -> seed -> planting details."""

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}
        self._seed_pending: dict[str, Any] = {}
        self._matches: dict[str, PlantProfile] = {}
        self._vendor_id: str | None = None
        self._vendor_name: str | None = None
        self._seed_id: str | None = None
        self._seed_variety: str | None = None
        self._profile: PlantProfile | None = None

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
        if not self._beds():
            return self.async_abort(reason="no_beds")
        return await self.async_step_vendor()

    # Step 1: vendor -------------------------------------------------------

    async def async_step_vendor(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            choice = user_input[CONF_VENDOR_ID]
            if choice == ADD_NEW:
                return await self.async_step_vendor_new()
            self._vendor_id = choice
            self._vendor_name = _vendor_name(self._get_entry(), choice)
            return await self.async_step_seed()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VENDOR_ID, default=VENDOR_UNKNOWN_ID
                ): _vendor_select(self._get_entry())
            }
        )
        return self.async_show_form(step_id="vendor", data_schema=schema)

    async def async_step_vendor_new(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._vendor_id, self._vendor_name = _add_vendor(
                self.hass, self._get_entry(), user_input[CONF_NAME],
                user_input.get(CONF_URL),
            )
            return await self.async_step_seed()
        return self.async_show_form(
            step_id="vendor_new",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME): str, vol.Optional(CONF_URL): str}
            ),
        )

    # Step 2: seed ---------------------------------------------------------

    async def async_step_seed(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            choice = user_input[CONF_SEED_ID]
            if choice == ADD_NEW:
                return await self.async_step_seed_new()
            sub = self._get_entry().subentries[choice]
            self._seed_id = choice
            self._profile = PlantProfile.from_dict(sub.data["profile"])
            self._seed_variety = sub.data.get(CONF_VARIETY)
            return await self.async_step_details()
        schema = vol.Schema(
            {
                vol.Required(CONF_SEED_ID): _seed_select_for_vendor(
                    self._get_entry(), self._vendor_id
                )
            }
        )
        return self.async_show_form(step_id="seed", data_schema=schema)

    async def async_step_seed_new(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._seed_pending = user_input
            return await self.async_step_seed_pick()
        return self.async_show_form(
            step_id="seed_new",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PLANT_QUERY): str,
                    vol.Required(CONF_VARIETY): str,
                    vol.Optional(CONF_SKU): str,
                    vol.Optional(CONF_URL): str,
                }
            ),
        )

    async def async_step_seed_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            profile = self._matches[user_input[CONF_PLANT_SOURCE_ID]]
            self._seed_variety = self._seed_pending[CONF_VARIETY]
            self._seed_id = await _add_seed(
                self.hass,
                self._get_entry(),
                self._vendor_id,
                self._vendor_name,
                self._seed_variety,
                self._seed_pending.get(CONF_SKU),
                self._seed_pending.get(CONF_URL),
                profile,
            )
            self._profile = profile
            return await self.async_step_details()

        schema, note = await _plant_pick_schema(
            self.hass, self._get_entry(), self._seed_pending[CONF_PLANT_QUERY],
            self._matches,
        )
        if schema is None:
            return self.async_abort(reason="no_matches")
        return self.async_show_form(
            step_id="seed_pick",
            data_schema=schema,
            description_placeholders={"note": note},
        )

    # Step 3: planting details --------------------------------------------

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        beds = self._beds()
        if user_input is not None:
            self._pending = user_input
            return await self._create()

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
                vol.Required(
                    CONF_SUCCESSIONS, default=1
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=12, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_SUCCESSION_INTERVAL,
                    default=DEFAULT_SUCCESSION_INTERVAL_DAYS,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="details", data_schema=schema)

    # Creation / succession logic -----------------------------------------

    def _base_sow_date(self, season_year: int) -> date:
        """Compute the frost-relative sow date to stagger successions from."""
        options = self._get_entry().options
        frost = resolve_frost_dates(
            self.hass.config.latitude,
            season_year,
            _parse_iso(options.get(CONF_LAST_FROST)),
            _parse_iso(options.get(CONF_FIRST_FROST)),
        )
        method = self._pending.get(CONF_METHOD) or self._profile.method
        probe = Planting(id="probe", bed_id="", profile=self._profile, method=method)
        return compute_sow_date(self._profile, probe, frost)

    def _base_data(self) -> dict[str, Any]:
        method = self._pending.get(CONF_METHOD) or self._profile.method
        return {
            CONF_BED_ID: self._pending[CONF_BED_ID],
            "profile": self._profile.to_dict(),
            "method": method,
            "quantity": int(self._pending.get(CONF_QUANTITY, 1)),
            "season_year": int(self._pending[CONF_SEASON_YEAR]),
            "manual_overrides": {},
            "seed_id": self._seed_id,
            "seed_variety": self._seed_variety,
            "vendor_id": self._vendor_id,
            "vendor_name": self._vendor_name,
        }

    def _existing_same_crop(self, bed_id: str) -> int:
        """Count existing plantings of the same crop in the same bed."""
        count = 0
        for sub in self._get_entry().subentries.values():
            if sub.subentry_type != SUBENTRY_TYPE_PLANTING:
                continue
            data = sub.data
            if (
                data.get(CONF_BED_ID) == bed_id
                and data.get("profile", {}).get("source_id")
                == self._profile.source_id
            ):
                count += 1
        return count

    async def _create(self) -> SubentryFlowResult:
        entry = self._get_entry()
        if (runtime := getattr(entry, "runtime_data", None)) is not None:
            await runtime.store.async_cache_profile(self._profile)

        bed_id = self._pending[CONF_BED_ID]
        bed_name = self._beds().get(bed_id, "")
        successions = int(self._pending.get(CONF_SUCCESSIONS, 1))
        interval = int(
            self._pending.get(
                CONF_SUCCESSION_INTERVAL, DEFAULT_SUCCESSION_INTERVAL_DAYS
            )
        )
        label = _plant_label(self._seed_variety, self._profile.common_name)
        base = f"{label} — {bed_name}" if bed_name else label

        if successions > 1:
            base_sow = self._base_sow_date(int(self._pending[CONF_SEASON_YEAR]))
            # Create successions 2..N up front, pinning each sow date so the
            # whole run stays staggered regardless of later frost recomputes.
            for i in range(1, successions):
                data = self._base_data()
                data["manual_overrides"] = {
                    "sow": (base_sow + timedelta(days=i * interval)).isoformat()
                }
                self.hass.config_entries.async_add_subentry(
                    entry,
                    ConfigSubentry(
                        data=data,
                        subentry_type=SUBENTRY_TYPE_PLANTING,
                        title=f"{base} #{i + 1}",
                        unique_id=None,
                    ),
                )
            first = self._base_data()
            first["manual_overrides"] = {"sow": base_sow.isoformat()}
            return self.async_create_entry(title=f"{base} #1", data=first)

        # Single planting: disambiguate the title if the same crop already
        # grows in this bed by appending its sow date.
        title = base
        if self._existing_same_crop(bed_id):
            sow = self._base_sow_date(int(self._pending[CONF_SEASON_YEAR]))
            title = f"{base} ({sow.isoformat()})"
        return self.async_create_entry(title=title, data=self._base_data())
