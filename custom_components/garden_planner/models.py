"""Data models for the Garden Planner integration.

These dataclasses are deliberately free of any Home Assistant imports so the
scheduling logic that consumes them can be unit-tested in isolation. Every model
knows how to (de)serialize itself to a JSON-friendly ``dict`` for the ``Store``.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from .const import (
    ANCHOR_SPRING,
    METHOD_DIRECT,
    SUN_FULL,
    WATER_MEDIUM,
)


class Stage(str, Enum):
    """Lifecycle stage of a planting.

    Inherits from ``str`` so values serialize cleanly and compare to plain
    strings (handy for entity states and storage).
    """

    PLANNED = "planned"
    SOWN = "sown"
    GERMINATING = "germinating"
    SEEDLING = "seedling"
    TRANSPLANTED = "transplanted"
    GROWING = "growing"
    FLOWERING = "flowering"
    HARVESTING = "harvesting"
    DONE = "done"


# Ordered progression used when advancing/comparing stages.
STAGE_ORDER: list[Stage] = [
    Stage.PLANNED,
    Stage.SOWN,
    Stage.GERMINATING,
    Stage.SEEDLING,
    Stage.TRANSPLANTED,
    Stage.GROWING,
    Stage.FLOWERING,
    Stage.HARVESTING,
    Stage.DONE,
]


def _date_to_iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _date_from_iso(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass(slots=True)
class PlantProfile:
    """Normalized, provider-agnostic description of a plant/crop.

    All timing offsets are expressed relative to the local frost dates so the
    same profile produces correct calendar dates in any climate.
    """

    common_name: str
    source: str
    source_id: str
    scientific_name: str | None = None
    sun: str = SUN_FULL
    water: str = WATER_MEDIUM
    days_to_maturity: int | None = None
    method: str = METHOD_DIRECT
    # Which frost date the sow offset is measured from: "spring" (before the
    # last spring frost, the default) or "fall" (before the first fall frost,
    # for overwintering crops such as garlic).
    sow_anchor: str = ANCHOR_SPRING
    # True for crops sown one year and harvested the next (overwintering).
    overwinter: bool = False
    # Sow indoors/direct this many weeks *before* the sow-anchor frost.
    sow_weeks_before_last_frost: float | None = None
    # Move seedlings out this many weeks *after* the last spring frost
    # (negative => before). Only meaningful for transplant crops.
    transplant_weeks_after_last_frost: float | None = None
    # How long harvesting typically lasts once it begins.
    harvest_window_days: int = 21
    spacing_cm: float | None = None
    depth_cm: float | None = None
    frost_tolerant: bool = False
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlantProfile:
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(slots=True)
class Bed:
    """A garden bed. Backed by a config subentry (subentry_id == id)."""

    id: str
    name: str
    sun_exposure: str = SUN_FULL
    size: str | None = None
    orientation: str | None = None
    soil: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Bed:
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass(slots=True)
class ActionLogEntry:
    """A record of something the gardener did to a planting."""

    kind: str
    on: date

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "on": _date_to_iso(self.on)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionLogEntry:
        return cls(kind=data["kind"], on=_date_from_iso(data["on"]))


@dataclass(slots=True)
class Planting:
    """A specific plant grown in a bed for a given season.

    ``profile`` is embedded (a cached copy of the plant data) so a planting keeps
    working even if the upstream provider changes or goes offline.
    ``manual_overrides`` maps an action kind (``"sow"``/``"transplant"``/
    ``"harvest"``) to an explicit ISO date that always wins over computed dates.
    """

    id: str
    bed_id: str
    profile: PlantProfile
    method: str = METHOD_DIRECT
    quantity: int = 1
    season_year: int | None = None
    manual_overrides: dict[str, str] = field(default_factory=dict)
    action_log: list[ActionLogEntry] = field(default_factory=list)

    def override_date(self, kind: str) -> date | None:
        return _date_from_iso(self.manual_overrides.get(kind))

    def last_action(self, kind: str) -> date | None:
        dates = [e.on for e in self.action_log if e.kind == kind and e.on]
        return max(dates) if dates else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bed_id": self.bed_id,
            "profile": self.profile.to_dict(),
            "method": self.method,
            "quantity": self.quantity,
            "season_year": self.season_year,
            "manual_overrides": dict(self.manual_overrides),
            "action_log": [e.to_dict() for e in self.action_log],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Planting:
        return cls(
            id=data["id"],
            bed_id=data["bed_id"],
            profile=PlantProfile.from_dict(data["profile"]),
            method=data.get("method", METHOD_DIRECT),
            quantity=data.get("quantity", 1),
            season_year=data.get("season_year"),
            manual_overrides=dict(data.get("manual_overrides", {})),
            action_log=[
                ActionLogEntry.from_dict(e) for e in data.get("action_log", [])
            ],
        )


@dataclass(slots=True)
class GardenTask:
    """A computed, actionable task for a planting on a given date."""

    planting_id: str
    kind: str
    due_date: date
    done: bool = False
    label: str = ""
