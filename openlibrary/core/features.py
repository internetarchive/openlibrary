"""Pydantic-settings based feature flags.

Replaces the legacy ``infogami.utils.features`` module. Features are loaded
from the ``features:`` section of a YAML file (typically ``openlibrary.yml``)
using explicit pydantic-settings fields.

A single process-wide ``features`` instance is loaded at import time from
the path given by the ``OL_FEATURES_YAML_PATH`` environment variable
(falling back to ``conf/openlibrary.yml``). Access flags via dot notation::

    from openlibrary.core.features import features

    if features.stats:
        ...
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings

_LEGACY_FLAG_MAP = {
    "enabled": True,
    "disabled": False,
    "yes": True,
    "no": False,
    "true": True,
    "false": False,
}


class Features(BaseSettings):
    model_config = {"extra": "ignore"}

    debug: bool = False
    dev: bool = False
    lists: bool = True
    publishers: bool = False
    recentchanges_v2: bool = False
    stats: bool = True
    stats_header: bool = False
    superfast: bool = False
    undo: bool = True

    @classmethod
    def from_yaml(cls, path: Path | str) -> Features:
        """Load feature flags from the ``features:`` section of a YAML file.

        YAML keys are expected to match field names (kebab-case keys like
        ``stats-header`` are normalized to snake_case). Legacy string values
        like ``enabled``/``disabled`` are mapped to booleans; native YAML
        booleans and dict-based group gates are also handled.
        """
        data = yaml.safe_load(Path(path).read_text()) or {}
        features_dict = data.get("features") or {}
        normalized = {}
        for key, value in features_dict.items():
            normalized_key = key.replace("-", "_")
            if isinstance(value, str):
                normalized_value = _LEGACY_FLAG_MAP.get(value.lower(), bool(value))
            else:
                normalized_value = bool(value)
            normalized[normalized_key] = normalized_value
        return cls(**normalized)


def _load_features() -> Features:
    path = os.environ.get("OL_FEATURES_YAML_PATH", "conf/openlibrary.yml")
    return Features.from_yaml(path)


features: Features = _load_features()
