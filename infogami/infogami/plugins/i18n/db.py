from infogami.core import db
from infogami import tdb

def get_all_strings(site):
    type = db.get_type('i18n', create=True)
    return tdb.Things(type=type, parent=site)
