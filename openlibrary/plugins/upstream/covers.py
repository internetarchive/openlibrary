"""Handle book cover/author photo upload.
"""
import urllib, urllib2
import web
import simplejson

from infogami.utils import delegate
from utils import get_coverstore_url, render_template
from models import Image

def setup():
    pass
    
class add_cover(delegate.page):
    path = "(/books/OL\d+M)/add-cover"
    def GET(self, key):
        book = web.ctx.site.get(key)
        return render_template('covers/add', book)
        
    def POST(self, key):
        book = web.ctx.site.get(key)
        if not book:            
            raise web.notfound("")
            
        olid = key.split("/")[-1]

        i = web.input(file={}, url="")
        user = web.ctx.site.get_user()
        print i.file.filename, i.url, len(i.file.value)
        
        if i.file is not None:
            data = i.file.value
        else:
            data = None
            
        if i.url and i.url.strip() == "http://":
            i.url = ""

        upload_url = get_coverstore_url() + '/b/upload2'
        params = dict(author=user and user.key, data=data, source_url=i.url, olid=olid, ip=web.ctx.ip)
        try:
            response = urllib2.urlopen(upload_url, urllib.urlencode(params))
            out = response.read()
        except urllib2.HTTPError, e:
            out = e.read()
        
        data = simplejson.loads(out)
        coverid = data.get('id')
        if coverid:
            self.save(book, coverid)
        cover = Image("b", coverid)
        return render_template("covers/saved", cover)
        
    def save(self, book, coverid):
        book.covers = book.covers or []
        book.covers.append(coverid)
        book._save("Added new cover")

class add_photo(add_cover):
    path = "(/authors/OL\d+A)/add-photo"
    
    def save(self, author, photoid):
        author.photos = author.photos or []
        author.photos.append(photoid)
        author._save("Added new photo")

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
            return render_template("covers/saved", self.get_image(book))
        else:
            # ERROR
            pass
        
class manage_photos(manage_covers):
    path = "(/authors/OL\d+A)/manage-photos"
    
    def get_images(self, author):
        return author.get_photos()
    
    def get_image(self, author):
        return author.get_photo()
        
    def save_images(self, author, photos):
        author.photos = photos
        author._save('Update photos')