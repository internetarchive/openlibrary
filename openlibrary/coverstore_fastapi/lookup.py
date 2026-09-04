"""Lookups against Open Library and archive.org (no web.py / infogami).

Async ports of the relevant pieces of openlibrary/coverstore/code.py and
utils.py. The legacy direct-DB shortcut (oldb.py) is intentionally not ported;
these helpers always use the public OL HTTP API, which returns identical
results.
"""

import json
import logging

import httpx

from openlibrary.coverstore_fastapi import config, oldb, utils

logger = logging.getLogger("openlibrary.coverstore_fastapi.lookup")

# Number of images stored in one archive.org item
IMAGES_PER_ITEM = 10_000

# Number of images in one archive.org batch zip (used by archive.Cover.get_cover_url)
ARCHIVE_ITEM_SIZE = 1_000_000
ARCHIVE_BATCH_SIZE = 10_000

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={"User-Agent": utils.COVERSTORE_USER_AGENT},
            timeout=10,
            follow_redirects=False,
        )
    return _client


async def download_external_image(url: str) -> bytes:
    if not utils.is_allowed_cover_url(url):
        raise utils.DisallowedCoverUrl(f"URL {url} is not an allowed cover URL")

    resp = await get_client().get(url)
    return resp.content


def get_ol_url() -> str:
    return config.ol_url.removesuffix("/")


async def ol_things(key: str, value: str) -> list[str]:
    """Returns OL keys matching the given property value."""
    if oldb.is_supported():
        return await oldb.query(key, value)

    query = {
        "type": "/type/edition",
        key: value,
        "sort": "last_modified",
        "limit": 10,
    }
    try:
        resp = await get_client().get(
            f"{get_ol_url()}/api/things",
            params={"query": json.dumps(query)},
        )
        result = resp.json()
        return result["result"]
    except httpx.HTTPError, ValueError, OSError:
        logger.exception("ol_things failed")
        return []


async def ol_get(olkey: str) -> dict | None:
    """Returns the JSON doc for an OL key, or None."""
    if oldb.is_supported():
        return await oldb.get(olkey)

    try:
        resp = await get_client().get(f"{get_ol_url()}/{olkey}.json")
        return resp.json()
    except httpx.HTTPError, ValueError, OSError:
        logger.exception("ol_get failed")
        return None


async def get_cover_id(olkeys: list[str]) -> int | None:
    """Return the first cover id from the list of ol keys."""
    for olkey in olkeys:
        doc = await ol_get(olkey)
        if not doc:
            continue
        is_author = doc["key"].startswith("/authors")
        covers = doc.get("photos" if is_author else "covers", [])
        # Sometimes covers is stored as [None] or [-1] to indicate no covers.
        # If so, consider there are no covers.
        if covers and (covers[0] or -1) >= 0:
            return covers[0]
    return None


async def query_cover_id(category: str, key: str, value: str) -> int | None:
    """Async port of coverstore.code._query."""
    if key == "olid":
        prefixes = {"a": "/authors/", "b": "/books/", "w": "/works/"}
        if category in prefixes:
            olkey = prefixes[category] + value
            return await get_cover_id([olkey])
    elif category == "b":
        if key == "isbn":
            value = value.replace("-", "").strip()
            key = "isbn_"
        if key == "oclc":
            key = "oclc_numbers"
        olkeys = await ol_things(key, value)
        return await get_cover_id(olkeys)
    return None


async def get_ia_cover_url(identifier: str, size: str) -> str | None:
    try:
        resp = await get_client().get(f"https://archive.org/metadata/{identifier}/metadata")
        d = resp.json().get("result", {})
    except httpx.HTTPError, ValueError, OSError:
        return None

    # Not a text item or no images or scan is not complete yet
    if d.get("mediatype") != "texts" or d.get("repub_state", "4") not in ("4", "6") or "imagecount" not in d:
        return None

    w, h = config.image_sizes[size.upper()]
    return "https://archive.org/download/%s/page/cover_w%d_h%d.jpg" % (
        identifier,
        w,
        h,
    )


def zipview_url_from_id(coverid: int, size: str, protocol: str = "https") -> str:
    """Port of coverstore.code.zipview_url_from_id."""
    suffix = size and ("-" + size.upper())
    item_index = coverid // IMAGES_PER_ITEM
    itemid = "olcovers%d" % item_index
    zipfile = itemid + suffix + ".zip"
    filename = "%d%s.jpg" % (coverid, suffix)
    return f"{protocol}://archive.org/download/{itemid}/{zipfile}/{filename}"


def archive_cluster_url(cover_id: int, size: str = "", ext: str = "zip", protocol: str = "https") -> str:
    """Port of openlibrary.coverstore.archive.Cover.get_cover_url."""
    pcid = "%010d" % int(cover_id)
    img_filename = f"{pcid}{'-' + size.upper() if size else ''}.jpg"

    millions = cover_id // ARCHIVE_ITEM_SIZE
    item_id = f"{millions:04}"
    rem = cover_id - (ARCHIVE_ITEM_SIZE * millions)
    ten_thousands = rem // ARCHIVE_BATCH_SIZE
    batch_id = f"{ten_thousands:02}"

    prefix = f"{size.lower()}_" if size else ""
    folder = f"{prefix}covers_{item_id}"
    filename = f"{prefix}covers_{item_id}_{batch_id}.{ext}"
    return f"{protocol}://archive.org/download/{folder}/{filename}/{img_filename}"
