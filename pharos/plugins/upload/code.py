import web
import random
import string, re
import time
import os

from infogami import config
from infogami.utils import delegate
from infogami.utils.template import render

def random_name():
    return "".join(random.choice(string.lowercase) for i in range(10))

root = getattr(config, 'upload_root', "static/files/")
if not root.endswith('/'):
    root = root + '/'

def timestamp():
    return int(time.time() * 1000000)

class upload(delegate.page):
    def GET(self):
        i=web.input("name", file="/static/files/0.jpg")
        print render.imageupload(i.name, i.file)

    def POST(self):
        i = web.input(name="foo", file={})
        name = i.name
        assert re.match(r'^[a-zA-Z0-9_]*$', name), "bad name: " + repr(name)
        
        # divide 
        t = timestamp()
        dir = t % 1000
        path = "%s/%d/%s_%d.jpg" % (root, dir, name, t)
        
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        
        f = open(path, "w")
        f.write(i.file.value)
        f.close()
        print render.imageupload(name, '/' + path)
