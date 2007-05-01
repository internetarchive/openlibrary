from infogami.core import db
from infogami import tdb

def get_all_templates(site):
    template_type = db.get_type('template', create=True)
    return tdb.Things(type=template_type, parent=site)
