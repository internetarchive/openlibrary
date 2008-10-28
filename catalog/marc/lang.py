from catalog.infostore import get_site
import web

site = get_site()
lang = set(site.things({'type': '/type/language'}))

def add_lang(edition):
    if 'languages' not in edition:
        return
    key = edition['languages'][0]['key']
    if key in ('/l/   ', '/l/|||'):
        del edition['languages']
    elif key not in lang:
        del edition['languages']
