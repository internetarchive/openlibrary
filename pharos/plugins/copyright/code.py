import re
from infogami.utils import view
import copyrightstatus

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
