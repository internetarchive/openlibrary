"""Which fields /contribute offers, and what filling each is worth.

The scope is a JSON file so librarians can change it without a code change.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SCOPE_PATH = Path(__file__).parent / "scope.json"

FIELDS = ("languages", "number_of_pages", "publishers", "subtitle", "publish_date", "lccn", "oclc_numbers")


@dataclass(frozen=True)
class FieldScope:
    field: str
    enabled: bool
    points: int = 0  # Edition Scorecard weight; what a fill is worth to readers


@dataclass(frozen=True)
class Scope:
    fields: dict[str, FieldScope]

    def enabled_fields(self) -> list[str]:
        return [f for f in FIELDS if f in self.fields and self.fields[f].enabled]


def parse_scope(raw: dict) -> Scope:
    fields = {}
    for name, cfg in raw.get("fields", {}).items():
        if name not in FIELDS:
            raise ValueError(f"unknown field in scope: {name}")
        points = cfg.get("points", 0)
        if not isinstance(points, int) or points < 0:
            raise ValueError(f"points for {name} must be a non-negative integer: {points!r}")
        fields[name] = FieldScope(name, bool(cfg.get("enabled", False)), points)
    return Scope(fields)


@cache
def load_scope() -> Scope:
    with SCOPE_PATH.open() as f:
        return parse_scope(json.load(f))
