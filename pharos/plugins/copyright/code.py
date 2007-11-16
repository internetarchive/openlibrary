import re
from infogami.utils import view
import copyrightstatus

r_year = re.compile(r'(?:[^\d]|^)(\d\d\d\d)(?:[^\d]|$)')

@view.public
def copyright_status(edition):
    year = r_year.findall(edition.get('publication_date', ''))
    try:
        year = int(year)
    except ValueError:
        return None
    edition.publication_year = year
    return copyrightstatus.copyright_status(edition)
