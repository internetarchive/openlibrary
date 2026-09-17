import array
import datetime
import functools
import io
import itertools
import json
import logging
import mimetypes
import os
import textwrap
from email.utils import format_datetime, parsedate_to_datetime
from typing import Annotated, Final, Literal, cast

import httpx
import requests
import web
from fastapi import APIRouter, File, Form, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from PIL import Image, ImageDraw, ImageFont
from starlette.convertors import Convertor, register_url_convertor  # codespell:ignore convertors,convertor

from openlibrary.coverstore import config, db
from openlibrary.coverstore.coverlib import read_file, read_image, save_image
from openlibrary.coverstore.server import load_config
from openlibrary.coverstore.utils import (
    changequery,
    download_external_image,
    get_async_session,
    ol_get,
    ol_things,
    safeint,
)
from openlibrary.plugins.upstream.utils import setup_requests

if coverstore_config := os.getenv("COVERSTORE_CONFIG"):
    load_config(coverstore_config)

logger = logging.getLogger("coverstore")

# A size is spelled uppercase in a URL ("" being the original upload) and lowercase in
# db column names (filename_m) and tar paths (m_covers_0000_00.tar).
CoverSizeUpper = Literal["S", "M", "L", ""]
CoverSizeLower = Literal["s", "m", "l", ""]
SIZE_LOWER: Final[dict[CoverSizeUpper, CoverSizeLower]] = {"S": "s", "M": "m", "L": "l", "": ""}
# books, authors, works -- the rows of the coverstore `category` table. Annotating the
# handlers is what keeps an unknown category out of db.new(), where get_category_id()
# would miss and store the cover against a null category_id.
CoverCategory = Literal["a", "b", "w"]


class CoverSizeConvertor(Convertor[str]):  # codespell:ignore convertor
    """Restricts the ``-S``/``-M``/``-L`` filename suffix to the three real sizes.

    This has to constrain *routing*, not just validate, so that a size-less path
    falls through to the size-less route: an unrestricted size would make
    ``/b/isbn/978-0-14-118776-1.jpg`` match as ISBN ``978-0-14-118776`` at size
    ``1``, and ``/b/id/1-X.jpg`` as size ``X``. Unlike the category, which nothing
    falls through on and so is left to a ``Literal`` annotation.
    """

    regex = "[SML]"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("cover_size", CoverSizeConvertor())

router = APIRouter()


class PartialCoverDetails(web.storage):
    id: int
    # One of these 4
    filename: str
    filename_s: str
    filename_m: str
    filename_l: str
    created: datetime.datetime


async def get_cover_id(olkeys: list[str]) -> int | None:
    """Return the first cover from the list of ol keys."""
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


async def _query(category: CoverCategory, key: str, value: str) -> int | None:
    if key == "olid":
        prefixes = {"a": "/authors/", "b": "/books/", "w": "/works/"}
        return await get_cover_id([prefixes[category] + value])
    elif category == "b":
        if key == "isbn":
            value = value.replace("-", "").strip()
            key = "isbn_"
        if key == "oclc":
            key = "oclc_numbers"
        olkeys = await ol_things(key, value)
        return await get_cover_id(olkeys)
    return None


ERROR_EMPTY = 1, "No image found"
ERROR_INVALID_URL = 2, "Invalid URL"
ERROR_BAD_IMAGE = 3, "Invalid Image"


def _httpdate(date: datetime.datetime) -> str:
    return format_datetime(date.replace(tzinfo=datetime.UTC), usegmt=True)


def _expires_header(seconds: int) -> str:
    return _httpdate(datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=seconds))


def is_cached_copy_fresh(request: Request, date: datetime.datetime, etag: str) -> bool:
    """Whether the client's cached copy is still good, i.e. we can answer 304."""
    if_none_match = {x.strip('" ') for x in request.headers.get("if-none-match", "").split(",")}
    if "*" in if_none_match or etag in if_none_match:
        return True

    if if_modified_since := request.headers.get("if-modified-since", "").split(";")[0].strip():
        try:
            since = parsedate_to_datetime(if_modified_since)
        except TypeError, ValueError:
            return False
        if since.tzinfo is not None:
            since = since.astimezone(datetime.UTC).replace(tzinfo=None)
        # HTTP dates have no sub-second precision, so allow a second of slack
        return date - datetime.timedelta(seconds=1) <= since
    return False


@router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index() -> Response:
    return Response(
        content=(
            "<h1>Open Library Book Covers Repository</h1><div>See <a "
            'href="https://openlibrary.org/dev/docs/api/covers">Open Library Covers '
            "API</a> for details.</div>"
        ),
        media_type="text/html",
    )


@router.post("/{category}/upload2", include_in_schema=False)
async def upload2(
    category: CoverCategory,
    olid: Annotated[str | None, Form()] = None,
    author: Annotated[str | None, Form()] = None,
    data: Annotated[bytes | None, File()] = None,
    source_url: Annotated[str | None, Form()] = None,
    ip: Annotated[str | None, Form()] = None,
) -> Response:
    """openlibrary.org POSTs here via openlibrary/plugins/upstream/covers.py upload"""

    def error(code__msg: tuple[int, str]) -> JSONResponse:
        code, msg = code__msg
        body = json.dumps({"code": code, "message": msg})
        logger.exception("upload2 failed: " + body)
        return JSONResponse(status_code=400, content={"code": code, "message": msg})

    if source_url:
        try:
            data = await download_external_image(source_url)
        except:
            return error(ERROR_INVALID_URL)

    if not data:
        return error(ERROR_EMPTY)

    try:
        d = save_image(data, category=category, olid=olid, author=author, source_url=source_url, ip=ip)
    except ValueError:
        return error(ERROR_BAD_IMAGE)

    return JSONResponse(content={"ok": "true", "id": d.id})


def trim_microsecond(date):
    # ignore microseconds
    return datetime.datetime(*date.timetuple()[:6])


# Number of images stored in one archive.org item
IMAGES_PER_ITEM = 10_000


def zipview_url_from_id(coverid: int, size: CoverSizeUpper, protocol: str = "https") -> str:
    suffix = size and ("-" + size.upper())
    item_index = coverid // IMAGES_PER_ITEM
    itemid = "olcovers%d" % item_index
    zipfile = itemid + suffix + ".zip"
    filename = "%d%s.jpg" % (coverid, suffix)
    return f"{protocol}://archive.org/download/{itemid}/{zipfile}/{filename}"


async def get_ia_cover_url(identifier: str, size: Literal["S", "M", "L"]) -> str | None:
    url = f"https://archive.org/metadata/{identifier}/metadata"
    try:
        resp = await get_async_session().get(url)
        d = resp.json().get("result", {})
    except httpx.RequestError, ValueError:
        return None

    # Not a text item or no images or scan is not complete yet
    if d.get("mediatype") != "texts" or d.get("repub_state", "4") not in ("4", "6") or "imagecount" not in d:
        return None

    w, h = config.image_sizes[size.upper()]
    return "https://archive.org/download/%s/page/cover_w%d_h%d.jpg" % (identifier, w, h)


def get_details(coverid: int, size: CoverSizeLower = "") -> PartialCoverDetails | db.CoverDbDetails | None:
    # Use tar index if available to avoid db query. We have 0-6M images in tar balls.
    if coverid < 6_000_000 and size in "sml":
        path = get_tar_filename(coverid, size)

        if path:
            key = f"filename_{size}" if size else "filename"
            return cast(
                PartialCoverDetails,
                web.storage({"id": coverid, key: path, "created": datetime.datetime(2010, 1, 1)}),
            )

    return db.details(coverid)


def is_cover_in_cluster(coverid: int) -> bool:
    """Returns True if the cover is moved to archive.org cluster.
    It is found by looking at the config variable max_coveritem_index.
    """
    try:
        return coverid < IMAGES_PER_ITEM * config.get("max_coveritem_index", 0)
    except TypeError, ValueError:
        return False


def get_tar_filename(coverid: int, size: CoverSizeLower) -> str | None:
    """Returns tarfile:offset:size for given coverid."""
    tarindex = coverid // 10000
    index = coverid % 10000
    array_offset, array_size = get_tar_index(tarindex, size)

    offset = array_offset and array_offset[index]
    imgsize = array_size and array_size[index]

    prefix = f"{size}_covers" if size else "covers"

    if imgsize:
        name = "%010d" % coverid
        return f"{prefix}_{name[:4]}_{name[4:6]}.tar:{offset}:{imgsize}"
    return None


# mypy can't check callers against this signature: functools.cache's stub types its
# wrapper's __call__ as taking *args: Hashable, erasing the real parameter types.
# https://github.com/python/mypy/issues/16261
@functools.cache
def get_tar_index(tarindex: int, size: CoverSizeLower):
    assert config.data_root is not None
    path = os.path.join(config.data_root, get_tarindex_path(tarindex, size))
    if not os.path.exists(path):
        return None, None

    return parse_tarindex(open(path))


def get_tarindex_path(index: int, size: CoverSizeLower) -> str:
    name = "%06d" % index
    if size:
        prefix = f"{size}_covers"
    else:
        prefix = "covers"

    itemname = f"{prefix}_{name[:4]}"
    filename = f"{prefix}_{name[:4]}_{name[4:6]}.index"
    return os.path.join("items", itemname, filename)


def parse_tarindex(file: io.TextIOBase):
    """Takes tarindex file as file objects and returns array of offsets and array of sizes. The size of the returned arrays will be 10000."""
    array_offset = array.array("L", [0 for i in range(10000)])
    array_size = array.array("L", [0 for i in range(10000)])

    for line in file:
        line = line.strip()
        if line:
            name, offset, imgsize = line.split("\t")
            coverid = int(name[:10])  # First 10 chars is coverid, followed by ".jpg"
            index = coverid % 10000
            array_offset[index] = int(offset)
            array_size[index] = int(imgsize)
    return array_offset, array_size


def _serve_default(default: str) -> Response:
    """The fallback when no cover matched: the configured placeholder, a caller-supplied
    URL, or a plain 404."""

    def is_valid_url(url: str) -> bool:
        return url.startswith(("http://", "https://"))

    if config.default_image and default.lower() != "false" and not is_valid_url(default):
        media_type = mimetypes.guess_type(config.default_image)[0] or "image/jpeg"
        return Response(content=read_file(config.default_image), media_type=media_type)
    elif is_valid_url(default):
        return RedirectResponse(default, status_code=303)
    else:
        return Response(status_code=404)


async def _serve_cover(request: Request, category: CoverCategory, key: str, value: str, size: CoverSizeUpper, default: str) -> Response:
    key = key.lower()

    cover_id: int | None = None
    if key == "isbn":
        normalized_isbn = value.replace("-", "").strip()  # strip hyphens from ISBN
        cover_id = await _query(category, key, normalized_isbn)
    elif key == "ia":
        # archive.org only derives page images at a named size, so a size-less
        # request has nothing to redirect to.
        if size and (url := await get_ia_cover_url(value, size)):
            return RedirectResponse(url, status_code=302)
        cover_id = None  # notfound or redirect to default. handled later.
    elif key != "id":
        cover_id = await _query(category, key, value)
    else:
        cover_id = safeint(value)

    if cover_id is None or cover_id in config.blocked_covers:
        return _serve_default(default)

    # redirect to archive.org cluster for large size and original images whenever possible
    if size in ("L", "") and is_cover_in_cluster(cover_id):
        return RedirectResponse(zipview_url_from_id(cover_id, size, request.url.scheme), status_code=302)

    d = get_details(cover_id, SIZE_LOWER[size])
    if not d:
        return _serve_default(default)

    headers = {"Cache-Control": "public"}
    if key == "id":
        # set cache-for-ever headers only when requested with ID
        created = trim_microsecond(d.created)
        etag = f"{d.id}-{SIZE_LOWER[size]}"
        headers["Last-Modified"] = _httpdate(created)
        headers["ETag"] = f'"{etag}"'
        if is_cached_copy_fresh(request, created, etag):
            return Response(status_code=304, headers=headers)

        # this image is not going to expire in next 100 years.
        headers["Expires"] = _expires_header(100 * 365 * 24 * 3600)
    else:
        # Allow the client to cache the image for 10 mins to avoid further requests
        headers["Expires"] = _expires_header(10 * 60)

    try:
        from openlibrary.coverstore import archive

        if d.id >= 8_000_000 and d.uploaded:
            url = archive.Cover.get_cover_url(d.id, size=size, protocol=request.url.scheme)
            return RedirectResponse(url, status_code=302)
        return Response(content=read_image(d, size), media_type="image/jpeg", headers=headers)
    except OSError:
        return Response(status_code=404)


@router.api_route("/{category}/{key}/{value}-{size:cover_size}.jpg", methods=["GET", "HEAD"], include_in_schema=False)
async def cover_sized(
    request: Request,
    category: CoverCategory,
    key: str,
    value: str,
    size: Literal["S", "M", "L"],
    default: Annotated[str, Query()] = "true",
) -> Response:
    return await _serve_cover(request, category, key, value, size, default)


@router.api_route("/{category}/{key}/{value}.jpg", methods=["GET", "HEAD"], include_in_schema=False)
async def cover_unsized(
    request: Request,
    category: CoverCategory,
    key: str,
    value: str,
    default: Annotated[str, Query()] = "true",
) -> Response:
    return await _serve_cover(request, category, key, value, "", default)


@router.api_route("/{category}/{key}/{value}.json", methods=["GET", "HEAD"], include_in_schema=False)
async def cover_details(category: CoverCategory, key: str, value: str) -> Response:
    if key == "id":
        d = db.details(safeint(value))
        if not d:
            return Response(status_code=404)
        if isinstance(d["created"], datetime.datetime):
            d["created"] = d["created"].isoformat()
            d["last_modified"] = d["last_modified"].isoformat()
        return Response(content=json.dumps(d), media_type="application/json")

    cover_id = await _query(category, key, value)
    if cover_id is None:
        return Response(status_code=404)
    return RedirectResponse(f"/{category}/id/{cover_id}.json", status_code=302)


@router.api_route("/{category}/query", methods=["GET", "HEAD"], include_in_schema=False)
def query(
    category: CoverCategory,
    olid: Annotated[str | None, Query()] = None,
    offset: Annotated[str, Query()] = "0",
    limit: Annotated[str, Query()] = "10",
    callback: Annotated[str | None, Query()] = None,
    details: Annotated[str, Query()] = "false",
    cmd: Annotated[str | None, Query()] = None,
) -> Response:
    olids: str | list[str] | None = olid
    if olid and "," in olid:
        olids = olid.split(",")

    result = db.query(category, olids, offset=safeint(offset, 0), limit=min(safeint(limit, 10), 100))

    payload: dict | list
    if cmd == "ids":
        payload = {r.olid: r.id for r in result}
    elif details.lower() != "true":
        payload = [r.id for r in result]
    else:
        payload = [
            {
                "id": r.id,
                "olid": r.olid,
                "created": r.created.isoformat(),
                "last_modified": r.last_modified.isoformat(),
                "source_url": r.source_url,
                "width": r.width,
                "height": r.height,
            }
            for r in result
        ]

    json_data = json.dumps(payload)
    content = f"{callback}({json_data});" if callback else json_data
    return Response(content=content, media_type="text/javascript")


@router.post("/{category}/touch", include_in_schema=False)
def touch(
    request: Request,
    category: CoverCategory,
    id: Annotated[str | None, Form()] = None,
    redirect_url: Annotated[str | None, Form()] = None,
) -> Response:
    cover_id = id and safeint(id, None)
    if not cover_id:
        return Response(content=f"no such id: {cover_id}", media_type="text/plain")

    db.touch(cover_id)
    return RedirectResponse(redirect_url or request.headers.get("referer") or "/", status_code=303)


@router.post("/{category}/delete", include_in_schema=False)
def delete(
    category: CoverCategory,
    id: Annotated[str | None, Form()] = None,
    redirect_url: Annotated[str | None, Form()] = None,
) -> Response:
    cover_id = id and safeint(id, None)
    if not cover_id:
        return Response(content=f"no such id: {cover_id}", media_type="text/plain")

    db.delete(cover_id)
    if redirect_url:
        return RedirectResponse(redirect_url, status_code=303)
    return Response(content="cover has been deleted successfully.", media_type="text/plain")


@router.post("/{category}/upload", include_in_schema=False)
async def upload(
    request: Request,
    category: CoverCategory,
    olid: Annotated[str, Form()],
    author: Annotated[str | None, Form()] = None,
    file: Annotated[bytes | None, File()] = None,
    source_url: Annotated[str | None, Form()] = None,
    success_url: Annotated[str | None, Form()] = None,
    failure_url: Annotated[str | None, Form()] = None,
) -> Response:
    referer = request.headers.get("referer")
    success = success_url or referer or "/"
    failure = failure_url or referer or "/"

    def error(code__msg: tuple[int, str]) -> RedirectResponse:
        code, msg = code__msg
        logger.error("upload failed, olid=%s code=%s msg=%r", olid, code, msg)
        return RedirectResponse(changequery(failure, errcode=code, errmsg=msg), status_code=303)

    data = file
    if source_url:
        try:
            data = await download_external_image(source_url)
        except:
            return error(ERROR_INVALID_URL)

    if not data:
        return error(ERROR_EMPTY)

    try:
        save_image(
            data,
            category=category,
            olid=olid,
            author=author,
            source_url=source_url,
            ip=request.client and request.client.host,
        )
    except ValueError:
        return error(ERROR_BAD_IMAGE)

    return RedirectResponse(success, status_code=303)


def render_list_preview_image(lst_key: str):
    """This function takes a list of five books and puts their covers in the correct
    locations to create a new image for social-card"""
    from openlibrary.core.lists.model import List

    lst = cast(List, web.ctx.site.get(lst_key))
    five_covers = itertools.islice(
        (cover for seed in lst.get_seeds() if seed._type != "subject" and (cover := seed.get_cover())),
        0,
        5,
    )
    background = Image.open("/openlibrary/static/images/Twitter_Social_Card_Background.png")

    logo = Image.open("/openlibrary/static/images/Open_Library_logo.png")

    W, _H = background.size
    image = []
    for cover in five_covers:
        response = requests.get(f"https://covers.openlibrary.org/b/id/{cover.id}-M.jpg")
        image_bytes = io.BytesIO(response.content)

        img = Image.open(image_bytes)

        basewidth = 162
        wpercent = basewidth / float(img.size[0])
        hsize = int(float(img.size[1]) * float(wpercent))
        img = img.resize((basewidth, hsize), Image.Resampling.LANCZOS)
        image.append(img)

    max_height = 0
    for img in image:
        max_height = max(img.size[1], max_height)
    start_width = 63 + 92 * (5 - len(image))
    for img in image:
        background.paste(img, (start_width, 174 + max_height - img.size[1]))
        start_width += 184

    logo = logo.resize((120, 74), Image.Resampling.LANCZOS)
    background.paste(logo, (880, 14), logo)

    draw = ImageDraw.Draw(background)
    font_author = ImageFont.truetype("/openlibrary/static/fonts/NotoSans-LightItalic.ttf", 22)
    font_title = ImageFont.truetype("/openlibrary/static/fonts/NotoSans-SemiBold.ttf", 28)

    para = textwrap.wrap(lst.name or "Untitled List", width=45)
    current_h = 42

    author_text = "A list on Open Library"
    if owner := lst.get_owner():
        author_text = f"A list by {owner.displayname}"

    left, top, right, bottom = font_author.getbbox(author_text)
    w, h = right - left, bottom - top
    draw.text(((W - w) / 2, current_h), author_text, font=font_author, fill=(0, 0, 0))
    current_h += h + 5

    for line in para:
        left, top, right, bottom = font_title.getbbox(line)
        w, h = right - left, bottom - top
        draw.text(((W - w) / 2, current_h), line, font=font_title, fill=(0, 0, 0))
        current_h += h

    with io.BytesIO() as buf:
        background.save(buf, format="PNG")
        return buf.getvalue()


def setup():
    setup_requests(config)


setup()
