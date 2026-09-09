"""Serving covers stored in local tar balls.

Covers with ids < 6M were archived into per-batch tar balls on disk
(e.g. items/covers_0008/covers_0008_12.tar), with sibling ".index" text files
mapping each cover id to its byte offset and size inside the tar. This module
reads those indexes so the app can serve such covers without touching the
database.
"""

import array
import datetime
import functools
import io
import os
from typing import Any

from openlibrary.coverstore_fastapi import config


def find_cover(coverid: int, size: str) -> dict[str, Any] | None:
    """Returns a partial details dict if this cover lives in a local tar ball."""
    if coverid >= 6_000_000 or size not in "sml":
        return None

    path = get_filename(coverid, size)
    if path is None:
        return None

    key = f"filename_{size}" if size else "filename"
    # Archived tars predate individual upload timestamps.
    return {
        "id": coverid,
        key: path,
        "created": datetime.datetime(2010, 1, 1),
    }


def get_filename(coverid: int, size: str) -> str | None:
    """Returns tarfile:offset:size for given coverid."""
    tarindex = coverid // 10000
    index = coverid % 10000
    array_offset, array_size = get_index(tarindex, size)

    offset = array_offset and array_offset[index]
    imgsize = array_size and array_size[index]

    prefix = f"{size}_covers" if size else "covers"

    if imgsize:
        name = "%010d" % coverid
        return f"{prefix}_{name[:4]}_{name[4:6]}.tar:{offset}:{imgsize}"
    return None


@functools.cache
def get_index(tarindex: int, size: str) -> tuple[array.array, array.array] | tuple[None, None]:
    path = os.path.join(config.data_root or "", index_path(tarindex, size))
    if not os.path.exists(path):
        return None, None

    with open(path) as f:
        return parse(f)


def index_path(index: int, size: str) -> str:
    name = "%06d" % index
    prefix = f"{size}_covers" if size else "covers"

    itemname = f"{prefix}_{name[:4]}"
    filename = f"{prefix}_{name[:4]}_{name[4:6]}.index"
    return os.path.join("items", itemname, filename)


def parse(file: io.TextIOBase) -> tuple[array.array, array.array]:
    """Takes tarindex file as file objects and returns arrays of offsets and sizes. The size of the returned arrays will be 10000."""
    array_offset = array.array("L", [0] * 10000)
    array_size = array.array("L", [0] * 10000)

    for line in file:
        line = line.strip()
        if line:
            name, offset, imgsize = line.split("\t")
            coverid = int(name[:10])  # First 10 chars is coverid, followed by ".jpg"
            index = coverid % 10000
            array_offset[index] = int(offset)
            array_size[index] = int(imgsize)
    return array_offset, array_size
