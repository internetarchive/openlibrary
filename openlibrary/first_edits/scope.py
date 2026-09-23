"""Which fields First Edits offers, in which modes, and how much evidence each needs.

The scope is a JSON file so librarians can change it without a code change.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SCOPE_PATH = Path(__file__).parent / "scope.json"

MODES = ("fill", "check")
LEVELS = ("none", "weak", "fair", "strong")
FIELDS = ("languages", "number_of_pages", "publishers", "subtitle", "publish_date")


@dataclass(frozen=True)
class FieldScope:
    field: str
    enabled: bool
    modes: tuple[str, ...]
    min_level: str

    def allows(self, mode: str, level: str) -> bool:
        return self.enabled and mode in self.modes and LEVELS.index(level) >= LEVELS.index(self.min_level)


@dataclass(frozen=True)
class Scope:
    review_wait_days: int
    fields: dict[str, FieldScope]

    def enabled_fields(self) -> list[str]:
        return [f for f in FIELDS if f in self.fields and self.fields[f].enabled]


def parse_scope(raw: dict) -> Scope:
    fields = {}
    for name, cfg in raw.get("fields", {}).items():
        if name not in FIELDS:
            raise ValueError(f"unknown field in scope: {name}")
        modes = tuple(cfg.get("modes", ()))
        if bad := [m for m in modes if m not in MODES]:
            raise ValueError(f"unknown mode(s) for {name}: {bad}")
        level = cfg.get("min_level", "fair")
        if level not in LEVELS:
            raise ValueError(f"unknown min_level for {name}: {level}")
        fields[name] = FieldScope(name, bool(cfg.get("enabled", False)), modes, level)
    return Scope(int(raw.get("review_wait_days", 3)), fields)


@cache
def load_scope() -> Scope:
    with SCOPE_PATH.open() as f:
        return parse_scope(json.load(f))
