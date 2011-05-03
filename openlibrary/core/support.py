import couchdb

from infogami import config

def get_admin_database():
    admin_db = config.get("admin", {}).get("admin_db",None)
    if admin_db:
        return couchdb.Database(admin_db)
        

class Support(object):
    def __init__(self, db = None):
        if db:
            self.db = db
        else:
            self.db = get_admin_database()
        
        
    
