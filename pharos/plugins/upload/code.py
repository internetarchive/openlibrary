import web
import random
import string

from infogami import config
from infogami.utils import delegate
from infogami.utils.template import render

def random_name():
    return "".join(random.choice(string.lowercase) for i in range(10))

root = getattr(config, 'upload_root', "static/files/")
if not root.endswith('/'):
    root = root + '/'

class upload(delegate.page):
    def GET(self, site):
        i=web.input(file="/static/files/0.jpg")
        print render.imageupload(i.file)

    def POST(self, site):
        i = web.input(file={})
        name = random_name() + ".jpg"
        f = open(root + name, "w")
        f.write(i.file.value)
        f.close()
        print render.imageupload("/static/files/" + name)
