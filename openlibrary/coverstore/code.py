import array
import datetime
import io
import json
import logging
import os

import memcache
import requests

import web

from PIL import Image, ImageDraw, ImageFont
import textwrap


from openlibrary.coverstore import config, db, ratelimit
from openlibrary.coverstore.coverlib import read_file, read_image, save_image
from openlibrary.coverstore.utils import (
    changequery,
    download,
    ol_get,
    ol_things,
    random_string,
    rm_f,
    safeint,
)
from openlibrary.plugins.openlibrary.processors import CORSProcessor

logger = logging.getLogger("coverstore")

urls = (
    '/',
    'index',
    '/([^ /]*)/upload',
    'upload',
    '/([^ /]*)/upload2',
    'upload2',
    '/([^ /]*)/([a-zA-Z]*)/(.*)-([SML]).jpg',
    'cover',
    '/([^ /]*)/([a-zA-Z]*)/(.*)().jpg',
    'cover',
    '/([^ /]*)/([a-zA-Z]*)/(.*).json',
    'cover_details',
    '/([^ /]*)/query',
    'query',
    '/([^ /]*)/touch',
    'touch',
    '/([^ /]*)/delete',
    'delete',
)
app = web.application(urls, locals())

app.add_processor(CORSProcessor())


def get_cover_id(olkeys):
    """Return the first cover from the list of ol keys."""
    for olkey in olkeys:
        doc = ol_get(olkey)
        if not doc:
            continue
        is_author = doc['key'].startswith("/authors")
        covers = doc.get('photos' if is_author else 'covers', [])
        # Sometimes covers is stored as [None] or [-1] to indicate no covers.
        # If so, consider there are no covers.
        if covers and (covers[0] or -1) >= 0:
            return covers[0]


def _query(category, key, value):
    if key == 'olid':
        prefixes = dict(a="/authors/", b="/books/", w="/works/")
        if category in prefixes:
            olkey = prefixes[category] + value
            return get_cover_id([olkey])
    else:
        if category == 'b':
            if key == 'isbn':
                value = value.replace("-", "").strip()
                key = "isbn_"
            if key == 'oclc':
                key = 'oclc_numbers'
            olkeys = ol_things(key, value)
            return get_cover_id(olkeys)
    return None


ERROR_EMPTY = 1, "No image found"
ERROR_INVALID_URL = 2, "Invalid URL"
ERROR_BAD_IMAGE = 3, "Invalid Image"


class index:
    def GET(self):
        return '<h1>Open Library Book Covers Repository</h1><div>See <a href="https://openlibrary.org/dev/docs/api/covers">Open Library Covers API</a> for details.</div>'


def _cleanup():
    web.ctx.pop("_fieldstorage", None)
    web.ctx.pop("_data", None)
    web.ctx.env = {}


class upload:
    def POST(self, category):
        i = web.input(
            'olid',
            author=None,
            file={},
            source_url=None,
            success_url=None,
            failure_url=None,
        )

        success_url = i.success_url or web.ctx.get('HTTP_REFERRER') or '/'
        failure_url = i.failure_url or web.ctx.get('HTTP_REFERRER') or '/'

        def error(code__msg):
            (code, msg) = code__msg
            print("ERROR: upload failed, ", i.olid, code, repr(msg), file=web.debug)
            _cleanup()
            url = changequery(failure_url, errcode=code, errmsg=msg)
            raise web.seeother(url)

        if i.source_url:
            try:
                data = download(i.source_url)
            except:
                error(ERROR_INVALID_URL)
            source_url = i.source_url
        elif i.file is not None and i.file != {}:
            data = i.file.value
            source_url = None
        else:
            error(ERROR_EMPTY)

        if not data:
            error(ERROR_EMPTY)

        try:
            save_image(
                data,
                category=category,
                olid=i.olid,
                author=i.author,
                source_url=i.source_url,
                ip=web.ctx.ip,
            )
        except ValueError:
            error(ERROR_BAD_IMAGE)

        _cleanup()
        raise web.seeother(success_url)


class upload2:
    """openlibrary.org POSTs here via openlibrary/plugins/upstream/covers.py upload"""

    def POST(self, category):
        i = web.input(
            olid=None, author=None, data=None, source_url=None, ip=None, _unicode=False
        )

        web.ctx.pop("_fieldstorage", None)
        web.ctx.pop("_data", None)

        def error(code__msg):
            (code, msg) = code__msg
            _cleanup()
            e = web.badrequest()
            e.data = json.dumps({"code": code, "message": msg})
            logger.exception("upload2.POST() failed: " + e.data)
            raise e

        source_url = i.source_url
        data = i.data

        if source_url:
            try:
                data = download(source_url)
            except:
                error(ERROR_INVALID_URL)

        if not data:
            error(ERROR_EMPTY)

        try:
            d = save_image(
                data,
                category=category,
                olid=i.olid,
                author=i.author,
                source_url=i.source_url,
                ip=i.ip,
            )
        except ValueError:
            error(ERROR_BAD_IMAGE)

        _cleanup()
        return json.dumps({"ok": "true", "id": d.id})


def trim_microsecond(date):
    # ignore microseconds
    return datetime.datetime(*date.timetuple()[:6])


def zipview_url(item, zipfile, filename):
    # http or https
    protocol = web.ctx.protocol
    return (
        "%(protocol)s://archive.org/download/%(item)s/%(zipfile)s/%(filename)s"
        % locals()
    )


# Number of images stored in one archive.org item
IMAGES_PER_ITEM = 10000


def zipview_url_from_id(coverid, size):
    suffix = size and ("-" + size.upper())
    item_index = coverid / IMAGES_PER_ITEM
    itemid = "olcovers%d" % item_index
    zipfile = itemid + suffix + ".zip"
    filename = "%d%s.jpg" % (coverid, suffix)
    return zipview_url(itemid, zipfile, filename)


class cover:
    def GET(self, category, key, value, size):
        i = web.input(default="true")
        key = key.lower()

        def is_valid_url(url):
            return url.startswith(("http://", "https://"))

        def notfound():
            if (
                config.default_image
                and i.default.lower() != "false"
                and not is_valid_url(i.default)
            ):
                return read_file(config.default_image)
            elif is_valid_url(i.default):
                raise web.seeother(i.default)
            else:
                raise web.notfound("")

        def redirect(id):
            size_part = size and ("-" + size) or ""
            url = f"/{category}/id/{id}{size_part}.jpg"

            query = web.ctx.env.get('QUERY_STRING')
            if query:
                url += '?' + query
            raise web.found(url)

        if key == 'isbn':
            value = value.replace("-", "").strip()  # strip hyphens from ISBN
            # Disabling ratelimit as iptables is taking care of botnets.
            # value = self.ratelimit_query(category, key, value)
            value = self.query(category, key, value)

            # Redirect isbn requests to archive.org.
            # This will heavily reduce the load on coverstore server.
            # The max_coveritem_index config parameter specifies the latest
            # olcovers items uploaded to archive.org.
            if value and self.is_cover_in_cluster(value):
                url = zipview_url_from_id(int(value), size)
                raise web.found(url)
        elif key == 'ia':
            url = self.get_ia_cover_url(value, size)
            if url:
                raise web.found(url)
            else:
                value = None  # notfound or redirect to default. handled later.
        elif key != 'id':
            value = self.query(category, key, value)

        if value and safeint(value) in config.blocked_covers:
            raise web.notfound()

        # redirect to archive.org cluster for large size and original images whenever possible
        if value and (size == "L" or size == "") and self.is_cover_in_cluster(value):
            url = zipview_url_from_id(int(value), size)
            raise web.found(url)

        d = value and self.get_details(value, size.lower())
        if not d:
            return notfound()

        # set cache-for-ever headers only when requested with ID
        if key == 'id':
            etag = f"{d.id}-{size.lower()}"
            if not web.modified(trim_microsecond(d.created), etag=etag):
                raise web.notmodified()

            web.header('Cache-Control', 'public')
            web.expires(
                100 * 365 * 24 * 3600
            )  # this image is not going to expire in next 100 years.
        else:
            web.header('Cache-Control', 'public')
            web.expires(
                10 * 60
            )  # Allow the client to cache the image for 10 mins to avoid further requests

        web.header('Content-Type', 'image/jpeg')
        try:
            return read_image(d, size)
        except OSError:
            raise web.notfound()

    def get_ia_cover_url(self, identifier, size="M"):
        url = "https://archive.org/metadata/%s/metadata" % identifier
        try:
            d = requests.get(url).json().get("result", {})
        except (OSError, ValueError):
            return

        # Not a text item or no images or scan is not complete yet
        if (
            d.get("mediatype") != "texts"
            or d.get("repub_state", "4") not in ["4", "6"]
            or "imagecount" not in d
        ):
            return

        w, h = config.image_sizes[size.upper()]
        return "https://archive.org/download/%s/page/cover_w%d_h%d.jpg" % (
            identifier,
            w,
            h,
        )

    def get_details(self, coverid, size=""):
        try:
            coverid = int(coverid)
        except ValueError:
            return None

        # Use tar index if available to avoid db query. We have 0-6M images in tar balls.
        if isinstance(coverid, int) and coverid < 6000000 and size in "sml":
            path = self.get_tar_filename(coverid, size)

            if path:
                if size:
                    key = "filename_%s" % size
                else:
                    key = "filename"
                return web.storage(
                    {"id": coverid, key: path, "created": datetime.datetime(2010, 1, 1)}
                )

        return db.details(coverid)

    def is_cover_in_cluster(self, coverid):
        """Returns True if the cover is moved to archive.org cluster.
        It is found by looking at the config variable max_coveritem_index.
        """
        try:
            return int(coverid) < IMAGES_PER_ITEM * config.get("max_coveritem_index", 0)
        except (TypeError, ValueError):
            return False

    def get_tar_filename(self, coverid, size):
        """Returns tarfile:offset:size for given coverid."""
        tarindex = coverid / 10000
        index = coverid % 10000
        array_offset, array_size = get_tar_index(tarindex, size)

        offset = array_offset and array_offset[index]
        imgsize = array_size and array_size[index]

        if size:
            prefix = "%s_covers" % size
        else:
            prefix = "covers"

        if imgsize:
            name = "%010d" % coverid
            return f"{prefix}_{name[:4]}_{name[4:6]}.tar:{offset}:{imgsize}"

    def query(self, category, key, value):
        return _query(category, key, value)

    ratelimit_query = ratelimit.ratelimit()(query)


@web.memoize
def get_tar_index(tarindex, size):
    path = os.path.join(config.data_root, get_tarindex_path(tarindex, size))
    if not os.path.exists(path):
        return None, None

    return parse_tarindex(open(path))


def get_tarindex_path(index, size):
    name = "%06d" % index
    if size:
        prefix = "%s_covers" % size
    else:
        prefix = "covers"

    itemname = f"{prefix}_{name[:4]}"
    filename = f"{prefix}_{name[:4]}_{name[4:6]}.index"
    return os.path.join('items', itemname, filename)


def parse_tarindex(file):
    """Takes tarindex file as file objects and returns array of offsets and array of sizes. The size of the returned arrays will be 10000."""
    array_offset = array.array('L', [0 for i in range(10000)])
    array_size = array.array('L', [0 for i in range(10000)])

    for line in file:
        line = line.strip()
        if line:
            name, offset, imgsize = line.split("\t")
            coverid = int(name[:10])  # First 10 chars is coverid, followed by ".jpg"
            index = coverid % 10000
            array_offset[index] = int(offset)
            array_size[index] = int(imgsize)
    return array_offset, array_size


class cover_details:
    def GET(self, category, key, value):
        d = _query(category, key, value)

        if key == 'id':
            web.header('Content-Type', 'application/json')
            d = db.details(value)
            if d:
                if isinstance(d['created'], datetime.datetime):
                    d['created'] = d['created'].isoformat()
                    d['last_modified'] = d['last_modified'].isoformat()
                return json.dumps(d)
            else:
                raise web.notfound("")
        else:
            value = _query(category, key, value)
            if value is None:
                return web.notfound("")
            else:
                return web.found(f"/{category}/id/{value}.json")


class query:
    def GET(self, category):
        i = web.input(
            olid=None, offset=0, limit=10, callback=None, details="false", cmd=None
        )
        offset = safeint(i.offset, 0)
        limit = safeint(i.limit, 10)
        details = i.details.lower() == "true"

        if limit > 100:
            limit = 100

        if i.olid and ',' in i.olid:
            i.olid = i.olid.split(',')
        result = db.query(category, i.olid, offset=offset, limit=limit)

        if i.cmd == "ids":
            result = {r.olid: r.id for r in result}
        elif not details:
            result = [r.id for r in result]
        else:

            def process(r):
                return {
                    'id': r.id,
                    'olid': r.olid,
                    'created': r.created.isoformat(),
                    'last_modified': r.last_modified.isoformat(),
                    'source_url': r.source_url,
                    'width': r.width,
                    'height': r.height,
                }

            result = [process(r) for r in result]

        json_data = json.dumps(result)
        web.header('Content-Type', 'text/javascript')
        if i.callback:
            return f"{i.callback}({json_data});"
        else:
            return json_data


class touch:
    def POST(self, category):
        i = web.input(id=None, redirect_url=None)
        redirect_url = i.redirect_url or web.ctx.get('HTTP_REFERRER')

        id = i.id and safeint(i.id, None)
        if id:
            db.touch(id)
            raise web.seeother(redirect_url)
        else:
            return 'no such id: %s' % id


class delete:
    def POST(self, category):
        i = web.input(id=None, redirect_url=None)
        redirect_url = i.redirect_url

        id = i.id and safeint(i.id, None)
        if id:
            db.delete(id)
            if redirect_url:
                raise web.seeother(redirect_url)
            else:
                return 'cover has been deleted successfully.'
        else:
            return 'no such id: %s' % id


def render_list_preview_image(lst_key):
    """This function takes a list of five books and puts their covers in the correct
    locations to create a new image for social-card"""
    lst = web.ctx.site.get(lst_key)
    five_seeds = lst.seeds[0:5]
    background = Image.open("/openlibrary/static/images/Twitter_Social_Card_Background.png")

    logo = Image.open("/openlibrary/static/images/Open_Library_logo.png")

    W, H = background.size
    image = []
    for seed in five_seeds:
        cover = seed.get_cover()

        if  cover:
            response = requests.get(f"https://covers.openlibrary.org/b/id/{cover.id}-M.jpg")
            image_bytes = io.BytesIO(response.content)

            img = Image.open(image_bytes)

            basewidth = 162
            wpercent = (basewidth / float(img.size[0]))
            hsize = int(float(img.size[1]) * float(wpercent))
            img = img.resize((basewidth, hsize), Image.ANTIALIAS)
            image.append(img)
    max_height=0
    for img in image:
        if (img.size[1] > max_height):
            max_height = img.size[1]
    if len(image) == 5:
        background.paste(image[0], (63, 174 + max_height - image[0].size[1]))
        background.paste(image[1], (247, 174 + max_height - image[1].size[1]))
        background.paste(image[2], (431, 174 + max_height - image[2].size[1]))
        background.paste(image[3], (615, 174 + max_height - image[3].size[1]))
        background.paste(image[4], (799, 174 + max_height - image[4].size[1]))

    elif len(image) == 4:
        background.paste(image[0], (155, 174 + max_height - image[0].size[1]))
        background.paste(image[1], (339, 174 + max_height - image[1].size[1]))
        background.paste(image[2], (523, 174 + max_height - image[2].size[1]))
        background.paste(image[3], (707, 174 + max_height - image[3].size[1]))

    elif len(image) == 3:
        background.paste(image[0], (247, 174 + max_height - image[0].size[1]))
        background.paste(image[1], (431, 174 + max_height - image[1].size[1]))
        background.paste(image[2], (615, 174 + max_height - image[2].size[1]))

    elif len(image) == 2:
        background.paste(image[0], (339, 174 + max_height - image[0].size[1]))
        background.paste(image[1], (523, 174 + max_height - image[1].size[1]))

    else:
        background.paste(image[0], (431, 174 + max_height - image[0].size[1]))


    logo = logo.resize((120,74), Image.ANTIALIAS)
    background.paste(logo, (880, 14), logo)

    draw = ImageDraw.Draw(background)
    font_author = ImageFont.truetype("/openlibrary/static/fonts/NotoSans-LightItalic.ttf", 22)
    font_title = ImageFont.truetype("/openlibrary/static/fonts/NotoSans-SemiBold.ttf", 28)

    para = textwrap.wrap(lst.name, width=45)
    current_h = 42
    author_text = f"A list by {lst.get_owner().displayname}"
    w, h = draw.textsize(author_text, font=font_author)
    draw.text(((W - w) / 2, current_h), author_text, font=font_author, fill=(0,0,0))
    current_h += h + 5

    for line in para:
        w, h = draw.textsize(line, font=font_title)
        draw.text(((W - w) / 2, current_h), line, font=font_title, fill=(0,0,0))
        current_h += h

    with io.BytesIO() as buf:
        background.save(buf, format='PNG')
        return buf.getvalue()
