"""Configuration for the FastAPI coverstore.

Uses the exact same YAML configuration file format as the legacy coverstore
(conf/coverstore.yml).
"""

import os
from typing import Any

import yaml

image_sizes: dict[str, tuple[int, int]] = {"S": (116, 58), "M": (180, 360), "L": (500, 500)}

default_image: str | None = None
data_root: str | None = None

ol_url = "http://openlibrary.org/"

db_parameters: dict[str, Any] = {}

# When set, isbn/olid/oclc lookups query the Open Library database directly
# instead of going over HTTP to ol_url (same keys as legacy coverstore.yml).
ol_db_parameters: dict[str, Any] | None = None

# ids of the blocked covers
blocked_covers: list[int] = []

# Covers with id < IMAGES_PER_ITEM * max_coveritem_index are assumed to be
# moved to the archive.org cluster.
max_coveritem_index = 0


def load_config(configfile: str) -> None:
    with open(configfile) as in_file:
        d = yaml.safe_load(in_file) or {}
    for k, v in d.items():
        globals()[k] = v


if configfile := os.getenv("COVERSTORE_CONFIG"):
    load_config(configfile)
