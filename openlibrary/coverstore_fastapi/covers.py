"""Cover management (a web.py-free port of openlibrary/coverstore/coverlib.py)."""

import contextlib
import datetime
import os
from io import BytesIO
from logging import getLogger
from typing import Any

from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

from openlibrary.coverstore_fastapi import config, db
from openlibrary.coverstore_fastapi.utils import random_string

logger = getLogger("openlibrary.coverstore_fastapi.covers")

__all__ = ["read_file", "read_image", "save_image"]


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
    d["id"] = await db.new(
        category=d["category"],
        olid=d["olid"],
        filename=d["filename"],
        filename_s=d["filename_s"],
        filename_m=d["filename_m"],
        filename_l=d["filename_l"],
        author=d["author"],
        ip=d["ip"],
        source_url=d["source_url"],
        width=d["width"],
        height=d["height"],
    )
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
