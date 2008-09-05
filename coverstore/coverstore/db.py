import web

_categories = None

def get_category_id(category):
    global _categories
    if _categories is None:
        _categories = {}
        for c in web.select('category'):
            _categories[c.name] = c.id
    return _categories.get(category)
    
def new(category, olid, filename, author, ip, source_url):
    category_id = get_category_id(category)
    return web.insert('image', category_id=category_id, olid=olid, filename=filename, author=author, ip=ip, source_url=source_url)
    
def query(category, olid, offset=0, limit=10):
    category_id = get_category_id(category)
    result = web.select('image', 
        what='id',
        where='category_id=$category_id AND olid=$olid', 
        order='last_modified desc', 
        offset=offset,
        limit=limit,
        vars=locals())
    return [r.id for r in result]
    
def touch(id):
    """Sets the last_modified of the specified image to the current timestamp.
    By doing so, this image become comes in the top in query because the results are ordered by last_modified.
    """
    web.query("UPDATE image SET last_modified=(current_timestamp at time zone 'utc') where id=$id", vars=locals())

def get_filename(id):
    d = web.select('image', what='filename', where='id=$id',vars=locals())
    return d and d[0].filename or None
