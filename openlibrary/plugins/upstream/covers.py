"""Handle book cover/author photo upload."""

import os
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
        self.allowed_extensions = {'.jpg', '.jpeg', '.gif', '.png', '.webp'}

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


class add_cover(delegate.page):
    path = r"(/books/OL\d+M)/add-cover"
    cover_category = "b"

    def GET(self, key):
        book = web.ctx.site.get(key)
        return render_template('covers/add', book)

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

        data = self.upload(key, i)

        if coverid := data.get('id'):
            if isinstance(i.url, bytes):
                i.url = i.url.decode("utf-8")
            self.save(book, coverid, url=i.url)
            cover = Image(web.ctx.site, "b", coverid)
            return render_template("covers/saved", cover)
        else:
            return render_template("covers/add", book, {'url': i.url}, data)

    def upload(self, key, i):
        """Uploads a cover to coverstore and returns the response."""
        olid = key.split("/")[-1]

        if i.file is not None and hasattr(i.file, 'file'):
            file_data = i.file.file
            filename = i.file.filename

            validator = image_validator()
            try:
                validator.validate_extension(filename)
                validator.validate_size(file_data)
                validator.validate_image(file_data)
            except ValueError as e:
                return web.storage({'error': str(e)})

            data = file_data
        else:
            data = None

        if i.url and i.url.strip() == "https://":
            i.url = ""

        user = accounts.get_current_user()
        params = {
            "author": user and user.key,
            "source_url": i.url,
            "olid": olid,
            "ip": web.ctx.ip,
        }

        upload_url = f'{get_coverstore_url()}/{self.cover_category}/upload2'

        if upload_url.startswith("//"):
            upload_url = "http:" + upload_url

        try:
            files = {'data': data}
            response = requests.post(upload_url, data=params, files=files)
            return web.storage(response.json())
        except requests.HTTPError as e:
            logger.exception("Covers upload failed")
            return web.storage({'error': str(e)})

    def save(self, book, coverid, url=None):
        book.covers = [coverid] + [cover.id for cover in book.get_covers()]
        book._save(
            f'{get_coverstore_public_url()}/b/id/{coverid}-S.jpg',
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
        book._save('Update covers')

    def POST(self, key):
        book = web.ctx.site.get(key)
        if not book:
            raise web.notfound()

        images = web.input(image=[]).image
        if '-' in images:
            images = [int(id) for id in images[: images.index('-')]]
            self.save_images(book, images)
            return render_template("covers/saved", self.get_image(book), showinfo=False)
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
        author._save('Update photos')
