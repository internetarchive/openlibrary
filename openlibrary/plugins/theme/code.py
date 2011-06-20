import os
import re
import web
import simplejson

from infogami.utils import delegate
from infogami.utils.view import render_template, add_flash_message
from collections import defaultdict

class Git:
    def status(self):
        pass

def find_files(root, filter):
    '''Find all files that pass the filter function in and below
    the root directory.
    '''
    absroot = os.path.abspath(root)
    for path, dirs, files in os.walk(os.path.abspath(root)):
        path = root + web.lstrips(path, absroot)
        
        for file in files:
            f = os.path.join(path, file)
            if filter(f):
                yield f
                
class FilesList:
    def __init__(self):
        self.cache_file = ".theme"
            
    @property
    def files(self):
        if os.path.exists(self.cache_file):
            files = simplejson.loads(open(self.cache_file).read())
        else:
            files = list_files()
            f = open(self.cache_file, "w")
            f.write(simplejson.dumps(files))
            f.close()
            
        return files
        
    def organize_files(self, files):
        """Organizes files directory wise.
        """
        d = defaultdict(lambda: [])        
        for f in files:
            dir, filename = os.path.split(f)
            d[dir].append(filename)
            
        def index_dir(path):
            if path:
                dir, dirname = os.path.split(path)
                if dir not in d:
                    index_dir(dir)
                d[dir].append(dirname + "/")
        
        for f in d.keys():
            index_dir(f)
                    
        for files in d.values():
            files.sort(key=lambda f: (not f.endswith("/"), f))
                        
        return d
        
    def invalidate(self):
        os.unlink(self.cache_file)
                
    def list(self, path=None, recursive=False):
        path = path or ""
        if recursive:
            return [f for f in self.files if f.startswith(path)]
        else:
            if path.endswith("/"):
                path = path[:-1]
            return self.organize_files(self.files).get(path, [])
        
def list_files():
    dirs = [
        "openlibrary/plugins/openlibrary", 
        "openlibrary/plugins/upstream", 
        "openlibrary/plugins/admin",
        "openlibrary/plugins/worksearch",
        "openlibrary/admin", 
        "static"
    ]
        
    pattern = re.compile("(/templates/.*.html|/macros/.*.html|/js/.*.js|/css/.*.css)$")
    
    files = []
    for d in dirs:
        files += list(find_files(d, pattern.search))    
    return sorted(files)

class index(delegate.page):
    path = "/theme"
    
    def GET(self):
        raise web.seeother("/theme/files")
        
class file_view(delegate.page):
    path = "/theme/files(?:/(.*))?"
    
    def delegate(self, path):
        if path and not os.path.exists(path):
            raise web.notfound()

        i = web.input(_method="GET")
        name = web.ctx.method.upper() + "_" + i.get("m", "view")
        f = getattr(self, name, None)
        if f:
            return f(path)
        else:
            return self.GET_view(path)
            
    GET = POST = delegate
    
    def GET_view(self, path):
        fileslist = FilesList()
        if path is None:
            return render_template("theme/files", "", fileslist)
        elif os.path.isdir(path):
            return render_template("theme/files", path, fileslist)
        else:
            text = open(path).read()
            return render_template("theme/viewfile", path, text)

    def GET_edit(self, path):
        text = open(path).read()
        return render_template("theme/editfile", path, text)
        
    def POST_edit(self, path):
        i = web.input(_method="POST", text="")
        i.text = i.text.replace("\r\n", "\n").replace("\r", "\n")        
        f = open(path, 'w')
        f.write(i.text)
        f.close()        
        add_flash_message("info", "Page has been saved successfully.")
        raise web.seeother(web.ctx.path)

class gitview(delegate.page):
    path = "/theme/git"
    
    def GET(self):
        git = Git()
        return render_template("theme/git", git)
