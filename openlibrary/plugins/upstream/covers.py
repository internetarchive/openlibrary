"""Handle book cover/author photo upload.
"""
import urllib, urllib2
import web
import simplejson

from infogami.utils import delegate
from infogami.utils.view import safeint
from utils import get_coverstore_url, render_template
from models import Image
from openlibrary import accounts

def setup():
    pass
    
class add_cover(delegate.page):
    path = "(/books/OL\d+M)/add-cover"
    cover_category = "b"
    
    def GET(self, key):
        book = web.ctx.site.get(key)
        return render_template('covers/add', book)
        
    def POST(self, key):
        book = web.ctx.site.get(key)
        if not book:            
            raise web.notfound("")
            
        i = web.input(file={}, url="")
        
        # remove references to field storage objects
        web.ctx.pop("_fieldstorage", None)
        
        data = self.upload(key, i)
        coverid = data.get('id')
        
        if coverid:
            self.save(book, coverid, url=i.url)
            cover = Image(web.ctx.site, "b", coverid)
            return render_template("covers/saved", cover)
        else:
            return render_template("covers/add", book, {'url': i.url}, data)
            
    def upload(self, key, i):
        """Uploads a cover to coverstore and returns the response."""
        olid = key.split("/")[-1]
        
        if i.file is not None and hasattr(i.file, 'value'):
            data = i.file.value
        else:
            data = None
            
        if i.url and i.url.strip() == "http://":
            i.url = ""

        user = accounts.get_current_user()
        params = dict(author=user and user.key, data=data, source_url=i.url, olid=olid, ip=web.ctx.ip)

        upload_url = '%s/%s/upload2' % (get_coverstore_url(), self.cover_category)
        try:
            response = urllib2.urlopen(upload_url, urllib.urlencode(params))
            out = response.read()
        except urllib2.HTTPError, e:
            out = e.read()
        
        return web.storage(simplejson.loads(out))
        
    def save(self, book, coverid, url=None):
        book.covers = [coverid] + [cover.id for cover in book.get_covers()]
        book._save("Added new cover", action="add-cover", data={"url": url})

class add_work_cover(add_cover):
    path = "(/works/OL\d+W)/add-cover"
    cover_category = "w"
    
    def upload(self, key, i):
        if "coverid" in i and safeint(i.coverid):
            return web.storage(id=int(i.coverid))
        else:
            return add_cover.upload(self, key, i)

class add_photo(add_cover):
    path = "(/authors/OL\d+A)/add-photo"
    cover_category = "a"
    
    def save(self, author, photoid, url=None):
        author.photos = [photoid] + [photo.id for photo in author.get_photos()]
        author._save("Added new photo", action="add-photo", data={"url": url})

class manage_covers(delegate.page):
    path = "(/books/OL\d+M)/manage-covers"
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
            images = [int(id) for id in images[:images.index('-')]]
            self.save_images(book, images)
            return render_template("covers/saved", self.get_image(book), showinfo=False)
        else:
            # ERROR
            pass

class manage_work_covers(manage_covers):
    path = "(/works/OL\d+W)/manage-covers"


class manage_photos(manage_covers):
    path = "(/authors/OL\d+A)/manage-photos"
    
    def get_images(self, author):
        return author.get_photos()
    
    def get_image(self, author):
        return author.get_photo()
        
    def save_images(self, author, photos):
        author.photos = photos
        author._save('Update photos')
