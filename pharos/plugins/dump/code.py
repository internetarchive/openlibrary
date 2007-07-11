"""
Plugin to dump and load selective pages from infogami.
"""
import sys
import web
import infogami
from infogami.core import db
from infogami import tdb
from infogami import config

stdout = sys.stdout

@infogami.action
def dump(filename):
    """Dump specified pages and its dependencies."""

    web.load()
    site = db.get_site(config.site)

    visited = {}

    def visit_all(pages):
        for p in pages:
            if isinstance(p, tdb.Thing):
                visit(p)
            elif isinstance(p, list):
                visit_all(p)

    def visit(p):
        if p.id in visited:
            return 
        visited[p.id] = p
        visit(p.type)
        visit_all(p.d.values())

    pages = [db.get_version(site, p.strip()) for p in open(filename).readlines()]
    visit_all(pages)

    for p in visited.values():
        data = dict(p.d)
        data['__type__'] = p.type
        data['__name__'] = p.name
        print tdb.logger.format('thing', p.id, data),
           
@infogami.action
def load(filename):
    """Load a dump from a the given file to database."""
    from infogami.plugins.wikitemplates import code
    code.validation_enabled = False

    pages = {}
    for _, id, data in tdb.logger.parse(filename):
        type = data.pop('__type__')
        name = data.pop('__name__')
        pages[int(id)] = web.storage(id=int(id), name=name, type=type, d=data)

    web.load()
    site = db.get_site(config.site)
    
    mapping = {}
        
    def flat(items):
        """Makes a nested list flat.
            >>> x = flat([1, [2, 3, [4, 5], 6], 7])
            >>> list(x)
            [1, 2, 3, 4, 5, 6, 7]
        """
        for item in items:
            if isinstance(item, list):
                for x in flat(item):
                    yield x
            else:
                yield item
    
    def get_dependencies(page):
        d = [pages[v.id] for v in flat(page.d.values()) if isinstance(v, tdb.Thing)]
        if page.type.id != page.id:
            t =  pages[page.type.id]
            d = [t] + d
        return d
    
    def remap(v):
        if isinstance(v, tdb.Thing):
            return tdb.withID(mapping[v.id], lazy=True)
        elif isinstance(v, list):
            return [remap(x) for x in v]
        else:
            return v
        
    def new_version(page):
        print "new_version", page.name
        d = dict([(k, remap(v)) for k, v in page.d.items()])
        try:
            p = tdb.withName(page.name, site)
            p.setdata(d)
            
            # careful about type/type
            if page.type.id != page.id:
                p.type = remap(page.type)
        except tdb.NotFound:
            p = tdb.new(page.name, site, remap(page.type), d)
        
        p.save()
        return p.id
    
    def load_page(page):
        if page.id in mapping:
            return
        for p in get_dependencies(page):
            load_page(p)
        mapping[page.id] = new_version(page)
        
    web.transact()
    for p in pages.values():
        load_page(p)
    web.commit()

@infogami.action
def ls(path):
    site = db.get_site(config.site)
    pages = db.list_pages(site, path)
    for p in pages:
	print >> stdout, p.name
    
