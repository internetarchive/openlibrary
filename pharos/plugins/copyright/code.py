import re
from infogami.utils import view, delegate, template
import copyrightstatus
import web,db

r_year = re.compile(r'(?:[^\d]|^)(\d\d\d\d)(?:[^\d]|$)')

@view.public
def copyright_status(edition):
    year = r_year.findall(str(edition.get('publish_date', '')))
    try:
        year = int(year[0])
    except (IndexError, ValueError):
        return None
    edition.publish_year = year
    return copyrightstatus.copyright_status(edition)

class copyright(delegate.page):
    def POST(self, site):
        i = web.input(status='U',
                      edition='zzzzzzz')
        edition = db.get_thing(i.edition, db.get_type('type/edition'))
        t = dict(U='unknown-copyright',
                 PD='out-of-copyright',
                 C='in-copyright').get(i.status)
        assert t is not None
        return getattr(template.render, t)(i.edition, t, edition)
    GET = POST
