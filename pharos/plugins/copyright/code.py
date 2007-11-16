import re
from infogami.utils import view
import copyrightstatus

r_year = re.compile(r'(?:[^\d]|^)(\d\d\d\d)(?:[^\d]|$)')

@view.public
def copyright_status(edition):
    try:
        edition.publication_year = int(r_year.findall(edition.get('publication_date', '')))
        return copyrightstatus.copyright_status(edition)
    except:
        return None # unknown
