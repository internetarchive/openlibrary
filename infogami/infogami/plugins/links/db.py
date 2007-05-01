from infogami.core import db
from infogami import tdb

def get_links_type():
    linkstype = db.get_type('links') or db.new_type('links')
    linkstype.save()
    return linkstype
    
def new_links(page, links):
    # for links thing: parent=page, type=linkstype
    site = page.parent
    path = page.name
    d = {'site': site, 'path': path, 'links': list(links)}
    
    try:
        backlinks = tdb.withName("links", page)
        backlinks.setdata(d)
        backlinks.save()
    except tdb.NotFound:
        backlinks = tdb.new("links", page, get_links_type(), d)
        backlinks.save()

def get_links(site, path):
    return tdb.Things(type=get_links_type(), site=site, links=path)