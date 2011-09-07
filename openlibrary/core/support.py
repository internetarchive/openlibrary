import datetime
from collections import defaultdict

import couchdb
from couchdb.mapping import TextField, IntegerField, DateTimeField, ListField, DictField, Mapping, Document, ViewField
from couchdb.design import ViewDefinition

import web
from infogami import config


class InvalidCase(KeyError): pass
class DatabaseConnectionError(Exception): pass

@web.memoize
def get_admin_database():
    admin_db = config.get("admin", {}).get("admin_db",None)
    if admin_db:
        return couchdb.Database(admin_db)
    else:
        raise DatabaseConnectionError("No admin_db specified in config")
        

class Support(object):
    def __init__(self, db = None):
        if db:
            self.db = db
        else:
            self.db = get_admin_database()
    
    def create_case(self, creator_name, creator_email, creator_useragent, creator_username, subject, description, assignee, url = ""):
        "Creates a support case with the given parameters"
        seq = web.ctx.site.seq.next_value("support-case")
        created = datetime.datetime.utcnow()
        caseid = "case-%s"%seq
        c = Case.new(_id = caseid,
                     creator_name = creator_name,
                     creator_email = creator_email,
                     creator_useragent = creator_useragent,
                     creator_username  = creator_username,
                     subject = subject,
                     description = description,
                     assignee = assignee,
                     created = created,
                     status = "new",
                     url = url,
                     support_db = self.db)
        c.store(self.db)
        return c

    def get_case(self, caseid):
        "Returns the case with the given id"
        if not str(caseid).startswith("case"):
            caseid = "case-%s"%caseid
        c = Case.load(self.db, caseid)
        return c
        
    def get_all_cases(self, typ = "all", summarise = False, sortby = "lastmodified", desc = "false"):
        "Return all the cases in the system"
        if summarise:
            d = defaultdict(lambda: 0)
            v = ViewDefinition("cases", "sort-status", "", group_level = 1, stale = "ok")
            for i in v(self.db):
                d[i.key[0]] = i.value
            return d
        else:
            return Case.all(self.db, typ, sortby, desc)
            
            
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
    creator_username  = TextField()
    url               = TextField()
    created           = DateTimeField()
    history           = ListField(DictField(Mapping.build(at    = DateTimeField(),
                                                          by    = TextField(),
                                                          text  = TextField())))

    def __repr__(self):
        return "<Case ('%s')>"%self._id

    def change_status(self, new_status, by):
        self.status = new_status
        self.store(self.db)


    def reassign(self, new_assignee, by, text = ""):
        self.assignee = new_assignee
        entry = dict(by = by,
                     at = datetime.datetime.utcnow(),
                     text = "Case reassigned to '%s'\n\n%s"%(new_assignee, text))
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
        if not ret:
            raise InvalidCase("No case with id %s"%id)
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

    @property
    def caseno(self):
        "Returns case number"
        return int(self._id.replace("case-",""))

    @classmethod
    def new(cls, **kargs):
        ret = cls(**kargs)
        item = dict (at = ret.created,
                     by = ret.creator_name or ret.creator_email,
                     text = "Case created")
        ret.history.append(item)
        return ret

    @classmethod
    def all(cls, db, typ="all", sort = "status", desc = "false"):
        view = {"created"      : "cases/sort-created",
                "caseid"       : "cases/sort-caseid",
                "assigned"     : "cases/sort-assignee",
                "user"         : "cases/sort-creator",
                "lastmodified" : "cases/sort-lastmodified",
                "status"       : "cases/sort-status",
                "subject"      : "cases/sort-subject",
                "notes"        : "cases/sort-numnotes"}[sort]
        if sort == "status":
            extra = dict(reduce = False,
                         descending = desc)
        else:
            extra = dict(descending = desc)

        if typ == "all":
            view = view.replace("-","-all-") 
            result = cls.view(db, view, include_docs = True, stale = "ok", **extra)
            return result.rows
        elif typ == "new":
            startkey, endkey = (["new"], ["replied"])
        elif typ == "closed":
            startkey, endkey = (["closed"], ["new"])
        elif typ == "replied":
            startkey, endkey = (["replied"], False)
        else:
            raise KeyError("No such case type '%s'"%typ)

        if desc == "true":
            startkey, endkey = endkey, startkey
        if startkey:
            extra['startkey'] = startkey
        if endkey:
            extra['endkey'] = endkey
        result = cls.view(db, view, include_docs = True, stale = "ok", **extra)
        return result.rows
        
    def __eq__(self, second):
        return self._id == second._id
