"""Handle book cover/author photo upload."""

import os
from concurrent.futures import ThreadPoolExecutor
from logging import getLogger

import requests
import web
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from infogami.utils import delegate
from infogami.utils.view import safeint
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
# suggestions (Internet Archive scans, Wikidata, a work's edition covers) that
# stay listed whether or not they've been used.

IMAGE_CATEGORIES = {"/type/edition": "b", "/type/work": "w", "/type/author": "a"}


def image_field(doc) -> str:
    return "photos" if doc.type.key == "/type/author" else "covers"


def attached_images(doc) -> list[Image]:
    if doc.type.key == "/type/author":
        return doc.get_photos()
    if doc.type.key == "/type/work":
        return doc.get_covers(use_solr=False)
    return doc.get_covers()


def cover_suggestions(doc) -> list[web.storage]:
    """Images that can become this doc's cover without an upload, in display order."""
    if doc.type.key == "/type/edition" and doc.ocaid:
        base = f"https://archive.org/download/{doc.ocaid}/page"
        return [
            web.storage(name=f"archive-{page}", kind=f"archive_{page}", source_url=f"{base}/{page}", thumb=f"{base}/{page}_w360.jpg", image=None)
            for page in ("cover", "title")
        ]
    if doc.type.key == "/type/author":
        wikidata = doc.wikidata()
        urls = wikidata.get_image_urls() if wikidata else []
        return [web.storage(name="wikidata", kind="wikidata", source_url=urls[0], thumb=f"{urls[0]}?width=360", image=None)] if urls else []
    if doc.type.key == "/type/work":
        return [web.storage(name=f"edition-{img.id}", kind="edition", source_url="", thumb=img.url("M"), image=img) for img in doc.get_edition_covers()]
    return []


def _fetch_infos(images: list[Image]) -> dict[int, web.storage]:
    """Coverstore metadata for each image, fetched in parallel; images it can't describe are left out."""
    if not images:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(images), 8)) as pool:
        infos = pool.map(lambda img: img.info(fetch_author=False), images)
    return {img.id: info for img, info in zip(images, infos) if info}


def _image_item(img: Image, info: web.storage | None, authors: dict, **extra) -> dict:
    author = info and authors.get(info.author)
    return {
        "id": f"img:{img.id}",
        "image_id": img.id,
        "thumb": img.url("M"),
        "large": img.url("L"),
        "source_url": (info and info.source_url) or None,
        "added_by": {"key": author.key, "name": author.displayname or author.key.split("/")[-1]} if author else None,
        "created": info and info.created.isoformat(),
        "width": info and info.width,
        "height": info and info.height,
        "attached": True,
        "removable": True,
        "kind": "upload",
    } | extra


def cover_manager_state(doc) -> dict:
    images = attached_images(doc)
    infos = _fetch_infos(images)
    author_keys = {info.author for info in infos.values() if info.author and info.author != "None"}
    authors = {a.key: a for a in doc._site.get_many(list(author_keys))} if author_keys else {}
    by_source = {infos[img.id].source_url: img for img in images if img.id in infos and infos[img.id].source_url}

    items, merged = [], set()
    for s in cover_suggestions(doc):
        if (img := s.image or by_source.get(s.source_url)) and img.id in infos:
            # A suggestion that's already been copied in shows as that copy.
            merged.add(img.id)
            items.append(_image_item(img, infos[img.id], authors, kind=s.kind, suggestion=s.name, removable=False))
        elif s.image:
            items.append(_image_item(s.image, None, authors, kind=s.kind, suggestion=s.name, attached=False, removable=False))
        else:
            items.append(
                {
                    "id": f"suggestion:{s.name}",
                    "kind": s.kind,
                    "suggestion": s.name,
                    "image_id": None,
                    "thumb": s.thumb,
                    "large": s.source_url,
                    "source_url": s.source_url,
                    "added_by": None,
                    "created": None,
                    "width": None,
                    "height": None,
                    "attached": False,
                    "removable": False,
                }
            )
    items += [_image_item(img, infos.get(img.id), authors) for img in images if img.id not in merged]

    if images:
        current = f"img:{images[0].id}"
    elif doc.type.key == "/type/edition" and doc.ocaid:
        # With no cover of its own, an edition shows its scan's cover page.
        current = "suggestion:archive-cover"
    elif doc.type.key == "/type/work" and (cover := doc.get_cover()):
        current = f"img:{cover.id}"
    else:
        current = None
    if current and not any(item["id"] == current for item in items):
        current = None
    return {"key": doc.key, "current": current, "items": items}


def apply_cover_changes(doc, selected: str, added: list[int], removed: list[int], user, ip: str) -> int | None:
    """Make `selected` the cover, attach `added` uploads and detach `removed`; returns the new cover id.

    Raises ValueError for an id that isn't this doc's to pick, and RuntimeError when the coverstore fails.
    """
    category = IMAGE_CATEGORIES[doc.type.key]
    olid = doc.key.split("/")[-1]
    current_ids = [img.id for img in attached_images(doc)]
    suggestions = {s.name: s for s in cover_suggestions(doc)}

    added = [i for i in dict.fromkeys(added) if i not in current_ids]
    for image_id in added:
        info = Image(doc._site, category, image_id).info(fetch_author=False)
        if not info or info.get("olid") != olid:
            raise ValueError(f"Image {image_id} was not uploaded for {doc.key}")

    imported_from = None
    if selected.startswith("suggestion:"):
        if not (s := suggestions.get(selected.removeprefix("suggestion:"))) or not s.source_url:
            raise ValueError(f"Unknown suggestion {selected}")
        infos = _fetch_infos([Image(doc._site, category, i) for i in current_ids])
        existing = next((i for i in current_ids if i in infos and infos[i].source_url == s.source_url), None)
        if existing:
            selected_id = existing
        else:
            result = upload_to_coverstore(category, olid, source_url=s.source_url, author_key=user and user.key, ip=ip)
            if not result.get("id"):
                raise RuntimeError(result.get("message") or result.get("error") or "Upload failed")
            selected_id = int(result.id)
            imported_from = s.source_url
    elif selected.startswith("img:") and selected[4:].isdigit():
        selected_id = int(selected[4:])
        pickable = set(current_ids) | set(added) | {s.image.id for s in suggestions.values() if s.image}
        if selected_id not in pickable:
            raise ValueError(f"Image {selected_id} is not one of this book's images")
    else:
        raise ValueError(f"Unknown selection {selected}")

    removed_ids = set(removed) - {selected_id}
    new_ids = [i for i in dict.fromkeys([selected_id, *current_ids, *added]) if i not in removed_ids]
    if new_ids == current_ids:
        return selected_id

    setattr(doc, image_field(doc), new_ids)
    if doc.type.key == "/type/author":
        is_new = bool(added or imported_from)
        doc._save("Added new photo" if is_new else "Update photos", action="add-photo" if is_new else "update-author-photos", data={"url": imported_from})
    elif selected_id in added or imported_from:
        # Recent changes renders an add-cover comment as the cover's thumbnail.
        doc._save(f"{get_coverstore_public_url()}/b/id/{selected_id}-S.jpg", action="add-cover", data={"url": imported_from})
    else:
        doc._save("Update covers", action="update-book-covers")
    return selected_id


class add_cover(delegate.page):
    path = r"(/books/OL\d+M)/add-cover"
    cover_category = "b"

    def GET(self, key):
        book = web.ctx.site.get(key)
        return render_template("covers/add", book)

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

        if coverid := data.get("id"):
            self.save(book, coverid, url=i.url)
            cover = Image(web.ctx.site, "b", coverid)
            image_info = cover.info()
            return render_template("covers/saved", cover, image_info=image_info)
        else:
            return render_template("covers/add", book, {"url": i.url}, data)

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
        return upload_to_coverstore(self.cover_category, olid, data=data, source_url=i.url, author_key=user and user.key, ip=web.ctx.ip)

    def save(self, book, coverid, url=None):
        book.covers = [coverid] + [cover.id for cover in book.get_covers()]
        book._save(
            f"{get_coverstore_public_url()}/b/id/{coverid}-S.jpg",
            action="add-cover",
            data={"url": url},
        )


class add_work_cover(add_cover):
    path = r"(/works/OL\d+W)/add-cover"
    cover_category = "w"

    def upload(self, key, i):
        if "coverid" in i and safeint(i.coverid):
            return web.storage(id=int(i.coverid))
        else:
            return add_cover.upload(self, key, i)


class add_photo(add_cover):
    path = r"(/authors/OL\d+A)/add-photo"
    cover_category = "a"

    def GET(self, key):
        author = web.ctx.site.get(key)
        wikidata_images = author.wikidata().get_image_urls() if author and author.wikidata() else []
        return render_template("covers/add", author, {"wikidata_images": wikidata_images})

    def save(self, author, photoid, url=None):
        author.photos = [photoid] + [photo.id for photo in author.get_photos()]
        author._save("Added new photo", action="add-photo", data={"url": url})


class manage_covers(delegate.page):
    path = r"(/books/OL\d+M)/manage-covers"

    def GET(self, key):
        book = web.ctx.site.get(key)
        if not book:
            raise web.notfound()
        return render_template("covers/manage", key, self.get_images(book))

    def get_images(self, book):
        return book.get_covers()

    def get_image(self, book):
        return book.get_cover()

    def save_images(self, book, covers):
        book.covers = covers
        book._save("Update covers", action="update-book-covers")

    def POST(self, key):
        if not accounts.get_current_user():
            raise web.unauthorized()
        book = web.ctx.site.get(key)
        if not book:
            raise web.notfound()

        images = web.input(image=[]).image
        if "-" in images:
            images = [int(id) for id in images[: images.index("-")]]
            self.save_images(book, images)
            cover = self.get_image(book)
            return render_template("covers/saved", cover, image_info=None, showinfo=False)
        else:
            # ERROR
            pass


class manage_work_covers(manage_covers):
    path = r"(/works/OL\d+W)/manage-covers"


class manage_photos(manage_covers):
    path = r"(/authors/OL\d+A)/manage-photos"

    def get_images(self, author):
        return author.get_photos()

    def get_image(self, author):
        return author.get_photo()

    def save_images(self, author, photos):
        author.photos = photos
        author._save("Update photos", action="update-author-photos")
