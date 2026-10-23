"""Handle book cover/author photo upload."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from logging import getLogger

import requests
import web
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from infogami.utils import delegate
from openlibrary import accounts
from openlibrary.plugins.upstream.models import Image
from openlibrary.plugins.upstream.utils import (
    get_coverstore_public_url,
    get_coverstore_url,
    render_template,
)

logger = getLogger("openlibrary.plugins.upstream.covers")


def setup():
    pass


class image_validator:
    def __init__(self):
        self.max_file_size = 10 * 1024 * 1024  # 10 MB
        self.allowed_extensions = {".jpg", ".jpeg", ".gif", ".png", ".webp"}

    def validate_size(self, file_data):
        file_size = len(file_data.read())
        file_data.seek(0)
        if file_size > self.max_file_size:
            raise ValueError("File size exceeds 10MB limit")

    def validate_extension(self, filename):
        file_extension = os.path.splitext(filename)[1].lower()
        if file_extension not in self.allowed_extensions:
            raise ValueError("Unsupported file extension")

    def validate_image(self, file_data):
        try:
            image = PILImage.open(file_data)
            image.verify()
            file_data.seek(0)
        except UnidentifiedImageError:
            raise ValueError("Not a valid image file")


def upload_to_coverstore(category: str, olid: str, *, data=None, source_url: str = "", author_key: str | None = None, ip: str | None = None) -> web.storage:
    """Store an image in the coverstore, from file data or a URL it downloads; returns its JSON reply."""
    params = {"author": author_key, "source_url": source_url, "olid": olid, "ip": ip}
    upload_url = f"{get_coverstore_url()}/{category}/upload2"
    if upload_url.startswith("//"):
        upload_url = "http:" + upload_url
    try:
        response = requests.post(upload_url, data=params, files={"data": data})
        return web.storage(response.json())
    except (requests.RequestException, ValueError) as e:
        logger.exception("Covers upload failed")
        return web.storage({"error": str(e)})


# The cover manager dialog: every image attached to a book or author, plus
# suggestions (Internet Archive scans, Wikidata) that stay listed whether or
# not they've been used.


@dataclass(frozen=True)
class Suggestion:
    """An image that can become the cover without an upload."""

    name: str
    kind: str
    source_url: str
    thumb: str


class RecordImages:
    """How one record type keeps its images: coverstore category, suggestions, and the edit a save writes."""

    category: str
    # The suggestion a record with no image of its own shows instead.
    fallback: str | None = None

    def images(self, doc) -> list[Image]:
        raise NotImplementedError

    def suggestions(self, doc) -> list[Suggestion]:
        return []

    def save(self, doc, ids: list[int], *, new_id: int | None = None, url: str | None = None) -> None:
        """Store `ids` as the record's images; `new_id` is an image this edit added, `url` where it was copied from."""
        raise NotImplementedError


class BookImages(RecordImages):
    def images(self, doc) -> list[Image]:
        return doc.get_covers()

    def save(self, doc, ids, *, new_id=None, url=None):
        doc.covers = ids
        if new_id:
            # Recent changes renders an add-cover comment as the cover's thumbnail.
            doc._save(f"{get_coverstore_public_url()}/{self.category}/id/{new_id}-S.jpg", action="add-cover", data={"url": url})
        else:
            doc._save("Update covers", action="update-book-covers")


class EditionImages(BookImages):
    category = "b"
    fallback = "archive-cover"

    def suggestions(self, doc):
        if not doc.ocaid:
            return []
        base = f"https://archive.org/download/{doc.ocaid}/page"
        return [Suggestion(f"archive-{page}", f"archive_{page}", f"{base}/{page}", f"{base}/{page}_w360.jpg") for page in ("cover", "title")]


class WorkImages(BookImages):
    category = "w"

    def images(self, doc):
        return doc.get_covers(use_solr=False)


class AuthorImages(RecordImages):
    category = "a"

    def images(self, doc):
        return doc.get_photos()

    def suggestions(self, doc):
        wikidata = doc.wikidata()
        urls = wikidata.get_image_urls() if wikidata else []
        return [Suggestion("wikidata", "wikidata", urls[0], f"{urls[0]}?width=360")] if urls else []

    def save(self, doc, ids, *, new_id=None, url=None):
        doc.photos = ids
        if new_id:
            doc._save("Added new photo", action="add-photo", data={"url": url})
        else:
            doc._save("Update photos", action="update-author-photos")


IMAGE_KINDS: dict[str, RecordImages] = {"/type/edition": EditionImages(), "/type/work": WorkImages(), "/type/author": AuthorImages()}


def _fetch_infos(images: list[Image]) -> dict[int, web.storage]:
    """Coverstore metadata for each image, fetched in parallel; images it can't describe are left out."""
    if not images:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(images), 8)) as pool:
        infos = pool.map(lambda img: img.info(fetch_author=False), images)
    return {img.id: info for img, info in zip(images, infos) if info}


def _imported(images: list[Image], infos: dict[int, web.storage]) -> dict[str, Image]:
    """Attached images by the URL they were copied from, so a used suggestion shows as its copy."""
    return {infos[img.id].source_url: img for img in images if img.id in infos and infos[img.id].source_url}


def image_item(img: Image, *, info: web.storage | None = None, added_by=None, kind: str = "upload") -> dict:
    """One attached (or just uploaded) image as the dialog lists it; `added_by` is a user or author record."""
    return {
        "id": f"img:{img.id}",
        "kind": kind,
        "image_id": img.id,
        "thumb": img.url("M"),
        "added_by": {"key": added_by.key, "name": added_by.displayname or added_by.key.split("/")[-1]} if added_by else None,
        "created": info.created.isoformat() if info else None,
    }


def cover_manager_state(doc) -> dict:
    kind = IMAGE_KINDS[doc.type.key]
    images = kind.images(doc)
    infos = _fetch_infos(images)
    author_keys = {info.author for info in infos.values() if info.author and info.author != "None"}
    authors = {a.key: a for a in doc._site.get_many(list(author_keys))} if author_keys else {}

    def item(img: Image, **extra) -> dict:
        info = infos.get(img.id)
        return image_item(img, info=info, added_by=info and authors.get(info.author), **extra)

    imported = _imported(images, infos)
    items, merged = [], set()
    for s in kind.suggestions(doc):
        if img := imported.get(s.source_url):
            merged.add(img.id)
            items.append(item(img, kind=s.kind))
        else:
            items.append({"id": f"suggestion:{s.name}", "kind": s.kind, "suggestion": s.name, "thumb": s.thumb})
    items += [item(img) for img in images if img.id not in merged]

    current: str | None = None
    if images:
        current = f"img:{images[0].id}"
    elif kind.fallback:
        current = f"suggestion:{kind.fallback}"
    if current and not any(item["id"] == current for item in items):
        current = None
    return {"key": doc.key, "current": current, "items": items}


def apply_cover_changes(doc, *, image_id: int | None = None, suggestion: str | None = None, added: list[int], removed: list[int], user, ip: str) -> int:
    """Make `image_id` (or a copy of `suggestion`) the cover, attach `added` uploads and detach `removed`; returns the cover id.

    Raises ValueError for an image that isn't this record's to pick, and RuntimeError when the coverstore fails.
    """
    kind = IMAGE_KINDS[doc.type.key]
    olid = doc.key.split("/")[-1]
    images = kind.images(doc)
    current_ids = [img.id for img in images]

    added = [i for i in dict.fromkeys(added) if i not in current_ids]
    for i in added:
        info = Image(doc._site, kind.category, i).info(fetch_author=False)
        if not info or info.get("olid") != olid:
            raise ValueError(f"Image {i} was not uploaded for {doc.key}")

    imported_from = None
    if suggestion is not None:
        if not (s := next((s for s in kind.suggestions(doc) if s.name == suggestion), None)):
            raise ValueError(f"Unknown suggestion {suggestion}")
        if img := _imported(images, _fetch_infos(images)).get(s.source_url):
            selected_id = img.id
        else:
            result = upload_to_coverstore(kind.category, olid, source_url=s.source_url, author_key=user and user.key, ip=ip)
            if not result.get("id"):
                raise RuntimeError(result.get("message") or result.get("error") or "Upload failed")
            selected_id = int(result.id)
            imported_from = s.source_url
    elif image_id in current_ids or image_id in added:
        selected_id = image_id
    else:
        raise ValueError(f"Image {image_id} is not one of {doc.key}'s images")

    removed_ids = set(removed) - {selected_id}
    new_ids = [i for i in dict.fromkeys([selected_id, *current_ids, *added]) if i not in removed_ids]
    if new_ids != current_ids:
        new_id = selected_id if imported_from or selected_id in added else next((i for i in added if i not in removed_ids), None)
        kind.save(doc, new_ids, new_id=new_id, url=imported_from)
    return selected_id


class add_cover(delegate.page):
    """POST-only: the form that used it is gone, but openlibrary-client and BWBCoverBot still post here and look for "Saved!"."""

    path = r"(/books/OL\d+M)/add-cover"
    kind: RecordImages = IMAGE_KINDS["/type/edition"]

    def POST(self, key):
        book = web.ctx.site.get(key)
        if not book:
            raise web.notfound("")

        user = accounts.get_current_user()
        if user and user.is_read_only():
            raise web.forbidden(message="Patron not permitted to upload images")

        i = web.input(file={}, url="")

        # remove references to field storage objects
        web.ctx.pop("_fieldstorage", None)

        # requests sends every `files=` entry as a file part, so a plain `url` field arrives as bytes.
        if isinstance(i.url, bytes):
            i.url = i.url.decode("utf-8")

        data = self.upload(key, i)

        if not (coverid := data.get("id")):
            raise web.badrequest(data.get("message") or data.get("error") or "Upload failed")
        self.save(book, coverid, url=i.url)
        return render_template("covers/saved", Image(web.ctx.site, self.kind.category, coverid))

    def upload(self, key, i):
        """Uploads a cover to coverstore and returns the response."""
        olid = key.split("/")[-1]

        # openlibrary-client's add_bookcover sends an empty file part alongside `url`.
        if (file_data := getattr(i.file, "file", None)) and file_data.read(1):
            file_data.seek(0)
            filename = i.file.filename

            validator = image_validator()
            try:
                validator.validate_extension(filename)
                validator.validate_size(file_data)
                validator.validate_image(file_data)
            except ValueError as e:
                return web.storage({"error": str(e)})

            data = file_data
        else:
            data = None

        if i.url and i.url.strip() == "https://":
            i.url = ""

        user = accounts.get_current_user()
        return upload_to_coverstore(self.kind.category, olid, data=data, source_url=i.url, author_key=user and user.key, ip=web.ctx.ip)

    def save(self, doc, coverid, url=None):
        self.kind.save(doc, [coverid] + [image.id for image in self.kind.images(doc)], new_id=coverid, url=url)


class add_work_cover(add_cover):
    path = r"(/works/OL\d+W)/add-cover"
    kind = IMAGE_KINDS["/type/work"]


class add_photo(add_cover):
    path = r"(/authors/OL\d+A)/add-photo"
    kind = IMAGE_KINDS["/type/author"]
