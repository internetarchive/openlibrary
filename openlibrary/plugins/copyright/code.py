import re
from infogami.utils import view, delegate
import copyrightstatus
import web
from infogami.utils.view import render

r_year = re.compile(r'(?:[^\d]|^)(\d\d\d\d)(?:[^\d]|$)')

@view.public
def copyright_status(edition):
    # computes copyright status of edition, first guessing year of
    # publication and storing it on edition.publish_year (i.e.
    # mutating its argument :-( ).

    year = r_year.findall(str(edition.get('publish_date', '')))
    try:
        year = int(year[0])
    except (IndexError, ValueError):
        return None
    #assert not hasattr(edition, 'publish_year')
    edition.publish_year = year
    return copyrightstatus.copyright_status(edition)

class copyright(delegate.page):
    def POST(self):
        i = web.input(status='U',
                      edition='zzzzzzz')

        edition = web.ctx.site.get(i.edition)
        status = i.status
        assert status in ('U','PD','C')
        return render.copyright(
            i.edition,
            status,
            edition)

    GET = POST
