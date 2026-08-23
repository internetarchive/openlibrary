"""The FastAPI coverstore application.

A 100% API-compatible reimplementation of openlibrary/coverstore/code.py.
Response quirks of the legacy web.py server (missing Content-Type headers on
plain responses, "text/html" vs "text/html; charset=utf-8", exact redirect
statuses, etc.) are intentionally reproduced.
"""

import array
import contextlib
import datetime
import functools
import io
import json
import logging
import os
import urllib.parse
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Path, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.convertors import Convertor, register_url_convertor
from starlette.datastructures import FormData, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from openlibrary.coverstore_fastapi import config, covers, db, lookup, oldb, utils

logger = logging.getLogger("coverstore")


class _LegacySegConvertor(Convertor):
    """Legacy URL segment pattern ([^ /]*) -- allows empty segments."""

    regex = r"[^ /]*"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


class _LegacyKeyConvertor(_LegacySegConvertor):
    regex = r"[a-zA-Z]*"


class _LegacyValueConvertor(_LegacySegConvertor):
    regex = r".*"


class _SMLConvertor(_LegacySegConvertor):
    regex = r"[SML]"


# These constraints must be part of the route regex itself so that
# non-matching URLs fall through to the next route exactly like web.py.
register_url_convertor("legacyseg", _LegacySegConvertor())
register_url_convertor("legacykey", _LegacyKeyConvertor())
register_url_convertor("legacyvalue", _LegacyValueConvertor())
register_url_convertor("sml", _SMLConvertor())


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await db.close_pool()
    await oldb.close()


app = FastAPI(
    title="Open Library Covers API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

ERROR_EMPTY = 1, "No image found"
ERROR_INVALID_URL = 2, "Invalid URL"
ERROR_BAD_IMAGE = 3, "Invalid Image"

INDEX_HTML = (
    '<h1>Open Library Book Covers Repository</h1><div>See <a href="https://openlibrary.org/dev/docs/api/covers">Open Library Covers API</a> for details.</div>'
)

# Legacy URL patterns allow empty categories/keys/values ([^ /]* and .*).
Category = Annotated[str, Path()]
Key = Annotated[str, Path()]
Value = Annotated[str, Path()]


class CoverDetailsResponse(BaseModel):
    """A cover row; field order matches the cover table columns."""

    id: int
    category_id: int | None = None
    olid: str | None = None
    filename: str | None = None
    filename_s: str | None = None
    filename_m: str | None = None
    filename_l: str | None = None
    author: str | None = None
    ip: str | None = None
    source_url: str | None = None
    source: str | None = None
    isbn: str | None = None
    width: int | None = None
    height: int | None = None
    failed: bool | None = None
    archived: bool | None = None
    uploaded: bool | None = None
    deleted: bool | None = None
    created: datetime.datetime
    last_modified: datetime.datetime


class CoverQueryDetail(BaseModel):
    id: int
    olid: str | None = None
    created: datetime.datetime
    last_modified: datetime.datetime
    source_url: str | None = None
    width: int | None = None
    height: int | None = None


class Upload2Success(BaseModel):
    ok: Literal["true"]
    id: int


def form_str(form: FormData, name: str) -> str | None:
    """Text field value from a parsed form (file parts yield None)."""
    value = form.get(name)
    return value if isinstance(value, str) else None


def bare(body: bytes | str = b"", status_code: int = 200) -> Response:
    """A response carrying no Content-Type header (legacy web.py plain responses)."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    return Response(content=body, status_code=status_code)


def html_response(body: str = "", status_code: int = 200, charset: bool = False, headers: dict[str, str] | None = None) -> Response:
    # NB: media_type is passed via headers because Starlette would append
    # "; charset=utf-8" to plain "text/html", while legacy responses keep
    # "text/html" and "text/html; charset=utf-8" apart.
    if charset:
        content_type = "text/html; charset=utf-8"
    else:
        content_type = "text/html"
    return Response(content=body, status_code=status_code, headers={"content-type": content_type, **(headers or {})})


def absolute_url(request: Request, url: str | None) -> str:
    """Mimics web.py redirect location building (home + path + query)."""
    if url and url.startswith(("http://", "https://")):
        return url
    home = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if not url:
        return home + request.url.path
    return urllib.parse.urljoin(home + request.url.path, url)


def seeother(request: Request, url: str | None, returned: bool = False) -> Response:
    # Raised web.seeother() yields an empty body; *returned* error objects get
    # rendered by web.py with their status text as the body.
    body = "303 See Other" if returned else ""
    return html_response(body, status_code=303, headers={"Location": absolute_url(request, url)})


def found(url: str) -> Response:
    """Port of web.found() -- a 302 whose body carries the status text."""
    return Response(
        content="302 Found",
        status_code=302,
        headers={"Location": url, "content-type": "text/html"},
    )


def is_valid_url(url: str) -> bool:
    return url.startswith(("http://", "https://"))


@app.middleware("http")
async def legacy_cors(request: Request, call_next):
    """Port of CORSProcessor(cors_everything=True).

    Adds the CORS headers to every response and answers every OPTIONS
    request with an empty 200, exactly like the legacy processor.
    """
    if request.method == "OPTIONS":
        response = bare()
    else:
        # Legacy web.py/gunicorn served HEAD like GET (body stripped by the
        # server); replicate by routing HEAD requests through GET.
        if request.method == "HEAD":
            request.scope["method"] = "GET"
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error")
            response = html_response("internal server error", status_code=500)
    response.headers.append("Access-Control-Allow-Origin", "*")
    response.headers.append("Access-Control-Allow-Method", "GET, OPTIONS")
    response.headers.append("Access-Control-Max-Age", "86400")  # one day
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    # web.py's plain-text error pages for routing failures.
    messages = {
        404: ("not found", True),
        405: ("method not allowed", False),
    }
    message, charset = messages.get(exc.status_code, ("", False))
    return html_response(
        message,
        status_code=exc.status_code,
        charset=charset,
        headers=dict(exc.headers or {}),
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception) -> Response:
    logger.exception("unhandled error")
    return html_response("internal server error", status_code=500)


@app.get("/health")
async def health() -> Response:
    try:
        await db.check()
        if oldb.is_supported():
            await oldb.check()
    except Exception:
        logger.exception("health check failed")
        return Response(content="database unavailable", status_code=503)
    return Response(content='{"status": "ok"}', media_type="application/json")


@app.get("/")
async def index() -> Response:
    return bare(INDEX_HTML)


@app.get("/{category:legacyseg}/{key:legacykey}/{value:legacyvalue}-{size:sml}.jpg")
async def cover_with_size(
    category: Category,
    key: Key,
    value: Value,
    size: Annotated[str, Path()],
    request: Request,
) -> Response:
    return await _cover(request, category, key.lower(), value, size)


@app.get("/{category:legacyseg}/{key:legacykey}/{value:legacyvalue}.jpg")
async def cover(category: Category, key: Key, value: Value, request: Request) -> Response:
    return await _cover(request, category, key.lower(), value, "")


@app.get("/{category:legacyseg}/{key:legacykey}/{value:legacyvalue}.json")
async def cover_details(request: Request, category: Category, key: Key, value: Value) -> Response:
    if key == "id":
        try:
            d = await db.details(value)
        except Exception:
            return html_response("internal server error", status_code=500)
        if d:
            details = CoverDetailsResponse.model_validate(dict(d))
            return JSONResponse(content=details.model_dump(mode="json"))
        else:
            return html_response("not found", status_code=404, charset=True)
    else:
        cover_id = await lookup.query_cover_id(category, key, value)
        if cover_id is None:
            return html_response("404 Not Found", status_code=404, charset=True)
        else:
            return found(absolute_url(request, f"/{category}/id/{cover_id}.json"))


@app.get("/{category:legacyseg}/query")
async def query(category: Category, request: Request) -> Response:
    params = request.query_params
    olid = params.get("olid")
    offset = utils.safeint(params.get("offset"), 0)
    limit = utils.safeint(params.get("limit"), 10)
    callback = params.get("callback")
    cmd = params.get("cmd")
    details = (params.get("details") or "false").lower() == "true"

    limit = min(limit, 100)

    olid_param: str | list[str] | None
    if olid and "," in olid:
        olid_param = olid.split(",")
    else:
        olid_param = olid
    result = await db.query(category, olid_param, offset=offset, limit=limit)

    payload: Any
    if cmd == "ids":
        payload = {r["olid"]: r["id"] for r in result}
    elif not details:
        payload = [r["id"] for r in result]
    else:
        payload = [CoverQueryDetail.model_validate(dict(r)).model_dump(mode="json") for r in result]

    data = json.dumps(payload, separators=(",", ":"))  # FastAPI/JSONResponse style
    if callback:
        return Response(content=f"{callback}({data});", headers={"content-type": "text/javascript"})
    else:
        return JSONResponse(content=payload, headers={"content-type": "text/javascript"})


@app.post("/{category:legacyseg}/upload")
async def upload(category: Category, request: Request) -> Response:
    form = await request.form()

    if "olid" not in form:
        # legacy web.input("olid") raises KeyError for the missing required
        # field, which the web.py app turns into a bad request.
        return html_response("bad request", status_code=400)

    olid = form_str(form, "olid")
    author = form_str(form, "author")
    source_url = form_str(form, "source_url")
    success_url = form_str(form, "success_url") or "/"
    failure_url = form_str(form, "failure_url") or "/"

    def error(code__msg: tuple[int, str]) -> Response:
        code, msg = code__msg
        logger.error("ERROR: upload failed, %s %s %r", olid, code, msg)
        url = utils.changequery(failure_url, errcode=code, errmsg=msg)
        return seeother(request, url)

    data: bytes | None
    file = form.get("file")
    if source_url:
        try:
            data = await lookup.download_external_image(source_url)
        except Exception:
            return error(ERROR_INVALID_URL)
    elif isinstance(file, UploadFile):
        data = await file.read()
    else:
        return error(ERROR_EMPTY)

    if not data:
        return error(ERROR_EMPTY)

    try:
        await covers.save_image(
            data,
            category=category,
            olid=str(olid),
            author=author,
            source_url=source_url,
            ip=request.client.host if request.client else None,
        )
    except ValueError:
        return error(ERROR_BAD_IMAGE)

    return seeother(request, success_url)


@app.post("/{category:legacyseg}/upload2")
async def upload2(category: Category, request: Request) -> Response:
    form = await request.form()

    olid = form_str(form, "olid")
    author = form_str(form, "author")
    source_url = form_str(form, "source_url")
    ip = form_str(form, "ip")

    def error(code__msg: tuple[int, str]) -> Response:
        code, msg = code__msg
        body = json.dumps({"code": code, "message": msg})
        logger.exception("upload2.POST() failed: " + body)
        return html_response(body, status_code=400)

    if source_url:
        try:
            data = await lookup.download_external_image(source_url)
        except Exception:
            return error(ERROR_INVALID_URL)
    else:
        raw = form.get("data")
        if raw is None:
            data = None
        elif isinstance(raw, str):
            # The legacy server chokes on text parts (the str reaches a
            # binary file write and dies with a TypeError -> 500).
            raise TypeError("a bytes-like object is required, not 'str'")
        else:
            data = await raw.read()

    if not data:
        return error(ERROR_EMPTY)

    try:
        d = await covers.save_image(
            data,
            category=category,
            olid=olid,
            author=author,
            source_url=source_url,
            ip=ip,
        )
    except ValueError:
        return error(ERROR_BAD_IMAGE)

    ok = Upload2Success(ok="true", id=d["id"])
    return JSONResponse(content=ok.model_dump())


@app.post("/{category:legacyseg}/touch")
async def touch(category: Category, request: Request) -> Response:
    form = await request.form()
    id_ = form_str(form, "id")
    redirect_url = form_str(form, "redirect_url")

    id = utils.safeint(id_, None)
    if id:
        await db.touch(id)
        return seeother(request, redirect_url)
    else:
        return bare(f"no such id: {id}")


@app.post("/{category:legacyseg}/delete")
async def delete(category: Category, request: Request) -> Response:
    form = await request.form()
    id_ = form_str(form, "id")
    redirect_url = form_str(form, "redirect_url")

    id = utils.safeint(id_, None)
    if id:
        await db.delete(id)
        if redirect_url:
            return seeother(request, redirect_url)
        else:
            return bare("cover has been deleted successfully.")
    else:
        return bare(f"no such id: {id}")


async def _cover(request: Request, category: str, key: str, value: str, size: str) -> Response:
    default = request.query_params.get("default", "true")

    async def notfound() -> Response:
        if config.default_image and default.lower() != "false" and not is_valid_url(default):
            return bare(await run_in_threadpool(covers.read_file, config.default_image))
        elif is_valid_url(default):
            return seeother(request, default, returned=True)
        else:
            return html_response("404 Not Found", status_code=404, charset=True)

    cover_id: int | None = None
    if key == "isbn":
        normalized_isbn = value.replace("-", "").strip()  # strip hyphens from ISBN
        cover_id = await lookup.query_cover_id(category, key, normalized_isbn)
    elif key == "ia":
        if ia_url := await lookup.get_ia_cover_url(value, size):
            return found(ia_url)
        else:
            cover_id = None  # notfound or redirect to default. handled later.
    elif key != "id":
        cover_id = await lookup.query_cover_id(category, key, value)
    else:
        cover_id = utils.safeint(value)

    if cover_id is None or cover_id in config.blocked_covers:
        return await notfound()

    protocol = request.url.scheme  # http or https

    # redirect to archive.org cluster for large size and original images whenever possible
    if size in ("L", "") and is_cover_in_cluster(cover_id):
        return found(lookup.zipview_url_from_id(cover_id, size, protocol))

    d = await get_details(cover_id, size.lower())
    if not d:
        return await notfound()

    headers: dict[str, str] = {}
    # set cache-for-ever headers only when requested with ID
    if key == "id":
        etag = f"{d['id']}-{size.lower()}"
        created = trim_microsecond(d["created"])
        if _not_modified(request, created, etag):
            headers["Last-Modified"] = utils.httpdate(created)
            headers["ETag"] = f'"{etag}"'
            return Response(status_code=304, headers=headers)

        headers["Last-Modified"] = utils.httpdate(created)
        headers["ETag"] = f'"{etag}"'
        headers["Cache-Control"] = "public"
        # this image is not going to expire in next 100 years.
        expires_in = 100 * 365 * 24 * 3600
    else:
        headers["Cache-Control"] = "public"
        # Allow the client to cache the image for 10 mins to avoid further requests
        expires_in = 10 * 60

    headers["Expires"] = utils.httpdate(utils.utcnow() + datetime.timedelta(seconds=expires_in))
    headers["Content-Type"] = "image/jpeg"

    try:
        if d["id"] >= 8_000_000 and d.get("uploaded"):
            return found(lookup.archive_cluster_url(d["id"], size=size, protocol=protocol))
        image = await run_in_threadpool(covers.read_image, d, size)
        return Response(content=image, headers=headers)
    except OSError:
        return html_response("404 Not Found", status_code=404, charset=True)


def _not_modified(request: Request, date: datetime.datetime, etag: str) -> bool:
    """Port of web.modified()'s cache validation."""
    n = {x.strip('" ') for x in request.headers.get("if-none-match", "").split(",")}
    m = utils.parse_httpdate(request.headers.get("if-modified-since", "").split(";")[0])
    validate = False
    if "*" in n or etag in n:
        validate = True
    # we subtract a second because HTTP dates don't have sub-second precision
    if date and m and date - datetime.timedelta(seconds=1) <= m:
        validate = True
    return validate


def trim_microsecond(date: datetime.datetime) -> datetime.datetime:
    # ignore microseconds
    return datetime.datetime(*date.timetuple()[:6])


def is_cover_in_cluster(coverid: int) -> bool:
    """Returns True if the cover is moved to archive.org cluster."""
    try:
        return coverid < lookup.IMAGES_PER_ITEM * config.max_coveritem_index
    except TypeError, ValueError:
        return False


async def get_details(coverid: int, size: str = "") -> dict[str, Any] | None:
    # Use tar index if available to avoid db query. We have 0-6M images in tar balls.
    if coverid < 6_000_000 and size in "sml":
        path = await run_in_threadpool(get_tar_filename, coverid, size)

        if path:
            key = f"filename_{size}" if size else "filename"
            return {
                "id": coverid,
                key: path,
                "created": datetime.datetime(2010, 1, 1),
            }

    return await db.details(coverid)


def get_tar_filename(coverid: int, size: str) -> str | None:
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


@functools.cache
def get_tar_index(tarindex: int, size: str) -> tuple[array.array, array.array] | tuple[None, None]:
    path = os.path.join(config.data_root or "", get_tarindex_path(tarindex, size))
    if not os.path.exists(path):
        return None, None

    with open(path) as f:
        return parse_tarindex(f)


def get_tarindex_path(index: int, size: str) -> str:
    name = "%06d" % index
    prefix = f"{size}_covers" if size else "covers"

    itemname = f"{prefix}_{name[:4]}"
    filename = f"{prefix}_{name[:4]}_{name[4:6]}.index"
    return os.path.join("items", itemname, filename)


def parse_tarindex(file: io.TextIOBase) -> tuple[array.array, array.array]:
    """Takes tarindex file as file objects and returns arrays of offsets and sizes. The size of the returned arrays will be 10000."""
    array_offset = array.array("L", [0 for _ in range(10000)])
    array_size = array.array("L", [0 for _ in range(10000)])

    for line in file:
        line = line.strip()
        if line:
            name, offset, imgsize = line.split("\t")
            coverid = int(name[:10])  # First 10 chars is coverid, followed by ".jpg"
            index = coverid % 10000
            array_offset[index] = int(offset)
            array_size[index] = int(imgsize)
    return array_offset, array_size
