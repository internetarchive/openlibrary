"""
Script to archive covers from local disk to warc disk.
"""
import web
import os

_cagegories = {}
def get_category(id):
    if id not in _cagegories:
        _cagegories[id] = web.select('category', where='id=$id', vars=locals())[0].name
    return _cagegories[id]
        
def move(cover, localdisk, warcdisk):
    print 'moving', cover.id, cover.filename
    data = localdisk.read(cover.filename) 
    category = get_category(cover.category_id)
    params = {
        'subject_uri': 'http://covers.openlibrary.org/%s/id/%d' % (category, cover.id),
        'olid': cover.olid,
        'ISBN': cover.isbn,
        'source': cover.source,
        'source_url': cover.source_url or '',
        'creation_date': cover.created.strftime('%Y%m%d%H%M%S'),
    }
    filename = warcdisk.write(data, params)
    print 'filename', filename
    web.update('cover', where='id=$cover.id', archived=True, filename=filename, vars=locals())

def archive(localdisk, warcdisk):
    covers = web.select('cover', where='archived=false', order='id')
    for cover in covers:
        move(cover, localdisk, warcdisk)
        path = os.path.join(localdisk.root, cover.filename)
        os.remove(path)

