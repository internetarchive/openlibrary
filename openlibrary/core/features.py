"""Pydantic-settings based feature flags.

Replaces the legacy ``infogami.utils.features`` module. Features are loaded
from the ``features:`` section of a YAML file (typically ``openlibrary.yml``)
using explicit pydantic-settings fields.

A single process-wide ``features`` instance is loaded at import time from
the path given by the ``OL_CONFIG`` environment variable
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


class Features(BaseSettings):
    model_config = {"extra": "ignore"}

    # debug: bool # disabled because we should probably get rid of it but we still have a `features.is_enabled("debug")` to deal with we didn't see in #12884
    # dev: bool # Warning: this is setup locally but not in testing/production
    # history_v2: bool # is set to admin in local/testing but in production it's "librarians". We might want to get rid of the flag?
    lists: bool  # we probably want to get rid of this one...
    # merge_authors: bool # merge-authors is set to librarians everywhere, we should probably get rid of it and just use is librarian in the few uses
    publishers: bool  # we probably want to get rid of this one...
    recentchanges_v2: bool  # might be able to get rid of this one, but it's used in infogami..
    stats: bool
    stats_header: bool
    superfast: bool
    # undo: bool # Warning: this is enabled locally but a usergroup of librarians in testing/production

    @classmethod
    def from_yaml(cls, path: Path | str) -> Features:
        """Load feature flags from the ``features:`` section of a YAML file.

        YAML keys are expected to match field names (kebab-case keys like
        ``stats-header`` are normalized to snake_case). String values
        ``enabled``/``disabled`` are mapped to booleans; unknown keys
        and unrecognized string values raise ``ValueError``.
        """
        data = yaml.safe_load(Path(path).read_text()) or {}
        features_dict = data.get("features") or {}
        normalized = {}
        for key, value in features_dict.items():
            normalized_key = key.replace("-", "_")
            if normalized_key not in cls.model_fields:
                continue
            if isinstance(value, str):
                if value.lower() == "enabled":
                    normalized_value = True
                elif value.lower() == "disabled":
                    normalized_value = False
                else:
                    raise ValueError(f"Unrecognized feature flag value {value!r} for {key!r}; expected 'enabled', 'disabled', or a native boolean")
            elif isinstance(value, bool):
                normalized_value = value
            else:
                raise ValueError(f"Invalid type for feature flag {key!r}: expected bool, got {type(value).__name__}")
            normalized[normalized_key] = normalized_value
        return cls(**normalized)


def _load_features() -> Features:
    path = os.environ.get("OL_CONFIG", "conf/openlibrary.yml")
    return Features.from_yaml(path)


features: Features = _load_features()
