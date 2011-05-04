import datetime

import couchdb
from couchdb.mapping import TextField, IntegerField, DateTimeField, ListField, DictField, Mapping, Document, ViewField

import web
from infogami import config

@web.memoize
def get_admin_database():
    admin_db = config.get("admin", {}).get("admin_db",None)
    if admin_db:
        return couchdb.Database(admin_db)
        

class Support(object):
    def __init__(self, db = None): #TBD : handle database failures
        if db:
            self.db = db
        else:
            self.db = get_admin_database()
    
    def create_case(self, creator_name, creator_email, creator_useragent, subject, description, assignee):
        "Creates a support case with the given parameters"
        seq = web.ctx.site.seq.next_value("support-case")
        created = datetime.datetime.utcnow()
        caseid = "case-%s"%seq
        c = Case(_id = caseid,
                 creator_name = creator_name,
                 creator_email = creator_email,
                 creator_useragent = creator_useragent,
                 subject = subject,
                 description = description,
                 assignee = assignee,
                 created = created,
                 status = "new",
                 support_db = self.db)
        c.store(self.db)
        return c

    def get_case(self, caseid):
        "Returns the case with the given id"
        if not str(caseid).startswith("case"):
            caseid = "case-%s"%caseid
        c = Case.load(self.db, caseid)
        return c
        
    def get_all_cases(self):
        "Return all the cases in the system"
        return Case.all(self.db)

            
    

class Case(Document):
    _id               = TextField()
    type              = TextField(default = "case")
    status            = TextField()
    assignee          = TextField()
    description       = TextField()
    subject           = TextField()
    creator_email     = TextField()
    creator_useragent = TextField()
    creator_name      = TextField()
    created           = DateTimeField()
    history           = ListField(DictField(Mapping.build(at    = DateTimeField(),
                                                          by    = TextField(),
                                                          text  = TextField())))

    def __init__(self, **kargs):
        super(Case, self).__init__(**kargs)
        item = dict (at = self.created,
                     by = self.creator_name or self.creator_email,
                     text = "Case created")
        self.history.append(item)

    def change_status(self, new_status, by):
        self.status = new_status
        entry = dict(by = by,
                     at = datetime.datetime.utcnow(),
                     text = "Case status changed to '%s'"%new_status)
        self.history.append(entry)
        self.store(self.db)


    def reassign(self, new_assignee, by):
        self.assignee = new_assignee
        entry = dict(by = by,
                     at = datetime.datetime.utcnow(),
                     text = "Case reassigned to '%s'"%new_assignee)
        self.history.append(entry)
        self.store(self.db)

    def add_worklog_entry(self, by, text):
        entry = dict(by = by,
                     at = datetime.datetime.utcnow(),
                     text = text)
        self.history.append(entry)
        self.store(self.db)
        
    # Override base class members to hold the database connection
    @classmethod
    def load(cls, db, id):
        ret = super(Case, cls).load(db, id)
        ret.db = db
        return ret

    def store(self, db):
        super(Case, self).store(db)
        self.db = db
        
    @property
    def last_modified(self):
        return self.history[-1].at

    @property
    def caseid(self):
        return self._id

    @ViewField.define('cases')
    def all(self, doc):
        if doc.get("type","") == "case":
            yield doc["_id"], doc


    def __eq__(self, second):
        return self._id == second._id

        
                 

        
             
        
        
        
