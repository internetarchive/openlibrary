"""Cover management: resolving cover keys and reading/writing image files."""

import contextlib
import datetime
import os
from dataclasses import dataclass
from io import BytesIO
from logging import getLogger
from typing import Any

from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

from openlibrary.coverstore_fastapi import config, db, lookup, tar_index
from openlibrary.coverstore_fastapi.utils import random_string, safeint

logger = getLogger("openlibrary.coverstore_fastapi.covers")


@dataclass
class CoverRef:
    """Result of resolving a cover-key URL segment to a cover."""

    id: int | None = None
    ia_url: str | None = None  # archive.org scan page for "ia"-keyed requests

    @property
    def missing(self) -> bool:
        return self.id is None and self.ia_url is None


async def resolve_cover(category: str, key: str, value: str, size: str) -> CoverRef:
    """Resolves a cover-key URL segment using the legacy strategy.

    Keys are "id" (numeric cover id), "isbn" (hyphens stripped, matched via
    OL properties), "ia" (archive.org item scan) or any OL property name
    ("olid", "oclc", ...).
    """
    if key == "ia":
        return CoverRef(ia_url=await lookup.get_ia_cover_url(value, size))

    if key == "isbn":
        value = value.replace("-", "").strip()  # strip hyphens from ISBN

    if key == "id":
        cover_id: int | None = safeint(value)
    else:
        cover_id = await lookup.query_cover_id(category, key, value)

    if cover_id is None or cover_id in config.blocked_covers:
        return CoverRef()
    return CoverRef(id=cover_id)


async def get_details(coverid: int, size: str = "") -> dict[str, Any] | None:
    """Locates a cover's metadata: tar-ball index first, database second."""
    d = await run_in_threadpool(tar_index.find_cover, coverid, size.lower())
    if d:
        return d

    return await db.details(coverid)


def is_cover_in_cluster(coverid: int) -> bool:
    """Returns True if the cover is served from the archive.org cluster."""
    try:
        return coverid < lookup.IMAGES_PER_ITEM * config.max_coveritem_index
    except TypeError, ValueError:
        return False


async def save_image(data: bytes, category: str, olid: str | None, author=None, ip=None, source_url=None) -> dict[str, Any]:
    """Save the provided image data, create thumbnails and add a db entry.

    ValueError is raised if the provided data is not a valid image.
    Blocking work (PIL resizing, file writes) runs in the threadpool.
    """
    prefix = make_path_prefix(olid)

    img = await run_in_threadpool(write_image, data, prefix)
    if img is None:
        raise ValueError("Bad Image")

    d: dict[str, Any] = {
        "category": category,
        "olid": olid,
        "author": author,
        "source_url": source_url,
        "ip": ip,
    }
    d["width"], d["height"] = img.size

    d["filename"] = prefix + ".jpg"
    d["filename_s"] = prefix + "-S.jpg"
    d["filename_m"] = prefix + "-M.jpg"
    d["filename_l"] = prefix + "-L.jpg"
    d["id"] = await db.new(d)
    return d


def make_path_prefix(olid: str | None, date: datetime.date | None = None) -> str:
    """Makes a file prefix for storing an image."""
    date = date or datetime.date.today()
    return "%04d/%02d/%02d/%s-%s" % (
        date.year,
        date.month,
        date.day,
        olid,
        random_string(5),
    )


def write_image(data: bytes, prefix: str) -> Image.Image | None:
    path_prefix = find_image_path(prefix)
    dirname = os.path.dirname(path_prefix)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    try:
        # save original image
        with open(path_prefix + ".jpg", "wb") as f:
            f.write(data)

        img = Image.open(BytesIO(data))

        try:
            # If the image EXIF contains a rotation, apply it so we get the correctly
            # oriented image
            ImageOps.exif_transpose(img, in_place=True)
        except (AttributeError, KeyError, OSError, ValueError) as e:
            logger.warning(f"Failed to apply EXIF orientation: {e}")

        if img.mode != "RGB":
            img = img.convert("RGB")  # type: ignore[assignment]

        for name, size in config.image_sizes.items():
            path = f"{path_prefix}-{name}.jpg"
            resize_image(img, size).save(path, quality=90)
        return img
    except OSError:
        logger.exception("write_image() failed")

        # cleanup
        rm_f(prefix + ".jpg")
        rm_f(prefix + "-S.jpg")
        rm_f(prefix + "-M.jpg")
        rm_f(prefix + "-L.jpg")

        return None


def resize_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resizes image to specified size while making sure that aspect ratio is maintained."""
    x, y = image.size
    if x > size[0]:
        y = max(y * size[0] // x, 1)
        x = size[0]
    if y > size[1]:
        x = max(x * size[1] // y, 1)
        y = size[1]
    return image.resize((x, y), Image.Resampling.LANCZOS)


def find_image_path(filename: str) -> str:
    if ":" in filename:
        return os.path.join(str(config.data_root), "items", filename.rsplit("_", 1)[0], filename)
    else:
        return os.path.join(str(config.data_root), "localdisk", filename)


def read_file(path: str) -> bytes:
    """Reads a whole file. Supports tar:path:offset:size paths."""
    if ":" in path:
        path, offset, size = path.rsplit(":", 2)
        with open(path, "rb") as f:
            f.seek(int(offset))
            return f.read(int(size))
    with open(path, "rb") as f:
        return f.read()


def read_image(d: Any, size: str) -> bytes:
    if size:
        filename = d[f"filename_{size.lower()}"] or d["filename"] + f"-{size.upper()}.jpg"
    else:
        filename = d["filename"]
    path = find_image_path(filename)
    return read_file(path)


def rm_f(filename: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(filename)
