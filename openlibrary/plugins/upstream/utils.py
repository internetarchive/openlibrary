import web
import simplejson

from infogami import config
from infogami.utils.view import render, public
from infogami.utils.macro import macro

@macro
@public
def render_template(name, *a, **kw):
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return render[name](*a, **kw)
    
@public
def json_encode(d):
    return simplejson.dumps(d)
    
def unflatten(d, seperator="--"):
    """Convert flattened data into nested form.
    
        >>> unflatten({"a": 1, "b--x": 2, "b--y": 3, "c--0": 4, "c--1": 5})
        {'a': 1, 'c': [4, 5], 'b': {'y': 3, 'x': 2}}
    """
    def isint(k):
        try:
            int(k)
            return True
        except ValueError:
            return False
        
    def setvalue(data, k, v):
        if '--' in k:
            k, k2 = k.split(seperator, 1)
            setvalue(data.setdefault(k, {}), k2, v)
        else:
            data[k] = v
            
    def makelist(d):
        """Convert d into a list if all the keys of d are integers."""
        if isinstance(d, dict):
            if all(isint(k) for k in d.keys()):
                return [makelist(d[k]) for k in sorted(d.keys(), key=int)]
            else:
                return web.storage((k, makelist(v)) for k, v in d.items())
        else:
            return d
            
    d2 = {}
    for k, v in d.items():
        setvalue(d2, k, v)
    return makelist(d2)
    
@public
def radio_input(checked=False, **params):
    params['type'] = 'radio'
    if checked:
        params['checked'] = "checked"
    return "<input %s />" % " ".join(['%s="%s"' % (k, web.websafe(v)) for k, v in params.items()])
    
@public
def radio_list(name, args, value):
    html = []
    for arg in args:
        if isinstance(arg, tuple):
            arg, label = arg
        else:
            label = arg
        html.append(radio_input())
        
@public
def get_coverstore_url():
    return config.get('coverstore_url', 'http://covers.openlibrary.org').rstrip('/')


@public
def get_history(page):
    """Returns initial and most recent history of given page.
    
    If the page has more than 5 revisions, first 2 and recent 3 changes are returned. 
    If the page has 5 or less than 
    """
    h = web.storage(revision=page.revision)
    if h.revision < 5:
        h.recent = web.ctx.site.versions({"key": page.key, "limit": 5})
        h.initial = []
    else:
        h.initial = web.ctx.site.versions({"key": page.key, "limit": 2, "offset": h.revision-2})
        h.recent = web.ctx.site.versions({"key": page.key, "limit": 3})
    return h

@public
def get_recent_author(doc):
    versions = web.ctx.site.versions({'key': doc.key, 'limit': 1})
    if versions:
        return versions[0].author
        
if __name__ == '__main__':
    import doctest
    doctest.testmod()
