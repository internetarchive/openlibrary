"""
Script to archive covers from local disk to warc disk.
"""
import web
import os

import db

_cagegories = {}
def get_category(id):
    if id not in _cagegories:
        _cagegories[id] = db.getdb().select('category', where='id=$id', vars=locals())[0].name
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
    db.getdb().update('cover', where='id=$cover.id', archived=True, filename=filename, vars=locals())

def archive(localdisk, warcdisk):
    covers = db.getdb().select('cover', where='archived=false', order='id')
    for cover in covers:
        try:
            move(cover, localdisk, warcdisk)
            path = os.path.join(localdisk.root, cover.filename)
            os.remove(path)
        except:
            print "failed to move", cover.filename
            import traceback
            traceback.print_exc()


