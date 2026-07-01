# 🌱 Garden Planner for Home Assistant

A native [HACS](https://hacs.xyz/) custom integration that turns Home Assistant
into a garden planner. Model your **garden beds** and **plantings**, and let the
integration tell you *when to sow, when to transplant, when to water, and when to
harvest* — with dates computed automatically from your local frost dates.

> Status: MVP. Entities, services, and a bundled dashboard card.

## Features

- **Garden beds** and **plantings** managed entirely through the Home Assistant
  UI (config subentries) — each becomes a device with its own entities.
- **Frost-relative scheduling**: sow / transplant / harvest dates are derived from
  a plant's profile and your last/first frost dates. Frost dates are estimated
  from your HA location and can be overridden.
- **Overwintering crops** (e.g. garlic, shallots) are sown relative to the *first
  fall frost* and harvested the next summer; their season reads as `2026–2027`.
- **Succession planting**: create several staggered plantings of a crop in one
  step (e.g. beets every 2 weeks ×3), each with a distinct, dated name.
- **Season lifecycle**: `archive_planting` saves a finished planting's summary +
  history and removes it; `clone_to_next_season` duplicates it into next year.
  History is never silently lost — deleting a planting from the UI archives its
  log automatically.
- **Pluggable plant data** with a bundled offline database (works with no API key
  or network), plus optional Perenual and OpenFarm providers. Every fetched plant
  is cached locally so plantings keep working if a provider goes down.
- **Per-planting entities**: growth stage, next task, days to next task, harvest
  date, days to harvest, an "action needed" binary sensor, one-tap log buttons,
  and manual date-override controls.
- **Native Calendar and To-do** entities for all upcoming garden tasks; checking a
  to-do item logs the action and advances the schedule.
- **Services and events** (`log_action`, `set_frost_dates`, `refresh_plant_data`,
  `archive_planting`, `clone_to_next_season`; `garden_planner_task_due`,
  `garden_planner_stage_change`) for automations.

## Installation (HACS)

1. In HACS → **Custom repositories**, add this repository as an **Integration**.
2. Install **Garden Planner** and restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Garden Planner.**
4. Open the integration, then use **Add garden bed** and **Add planting**
   (the "+" on the integration's subentries) to build out your garden.

## Configuration

- **Options** (⚙️ on the integration): choose the plant-data provider, enter a
  Perenual API key if used, pick units, and optionally override the frost dates.
- **Frost dates** default to an estimate based on your Home Assistant latitude.
  Set your known local dates for best accuracy.

## Garden timeline card

The integration ships a Lovelace card that draws a **season "Gantt" timeline** —
every planting as a bar on a shared calendar axis, grouped by bed, coloured by
phase (sow → growing → harvest), with a "today" marker. Succession runs and
overwintering spans (e.g. garlic crossing into next year) are visible at a glance.

The card is served and auto-registered by the integration, so **no separate HACS
plugin install is needed**. Add it to any dashboard:

```yaml
type: custom:garden-planner-card
title: My Garden      # optional
year: 2026            # optional; otherwise the range is derived from your plantings
```

If the card doesn't appear right after install, hard-refresh your browser (it's
loaded as a versioned frontend module).

## Example dashboard

```yaml
type: entities
title: Tomato — Raised Bed 1
entities:
  - sensor.tomato_stage
  - sensor.tomato_next_task
  - sensor.tomato_next_task_date
  - sensor.tomato_days_to_harvest
  - binary_sensor.tomato_action_needed
  - button.tomato_log_watering
```

Add the **Garden calendar** and **Garden tasks** to your dashboard with the
built-in Calendar and To-do list cards.

## Development

```bash
python -m pip install -r requirements_test.txt
pytest
```

The scheduling logic in `schedule.py` and the frost model in `frost.py` are pure
functions with no Home Assistant dependency and are covered by unit tests.

## License

MIT — see [LICENSE](LICENSE).
