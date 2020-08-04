from infogami.infobase.server import get_site

site = get_site('openlibrary.org')
lang = set(site.things({'type': '/type/language'}))

def add_lang(edition):
    if 'languages' not in edition:
        return
    key = edition['languages'][0]['key']
    if key in ('/l/   ', '/l/|||'):
        del edition['languages']
    elif key not in lang:
        del edition['languages']
