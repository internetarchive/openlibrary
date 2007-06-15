import web
import logger

class NotFound(Exception): pass
class BadData(Exception): pass

class Thing:
    @staticmethod
    def _reserved(attr):
        return attr.startswith('_') or attr in [
          'id', 'parent', 'name', 'type', 'latest_revision', 'v', 'h', 'd', 'latest', 'versions', 'save']
    
    def __init__(self, id, name, parent, type, d, v=None, latest_revision=0):
        self.id, self.name, self.parent, self.type, self.d, self.v, self.latest_revision = \
            id and int(id), name, parent, type, d, v, latest_revision
        self.h = (self.id and History(self.id)) or None
        self._dirty = False
        self.d = web.storage(self.d)
            
    def __repr__(self):
        dirty = (self._dirty and " dirty") or ""
        return '<Thing "%s" at %s%s>' % (self.name, self.id, dirty)

    def __str__(self): return self.name
    
    def __cmp__(self, other):
        return cmp(self.id, other.id)

    def __eq__(self, other):
        return self.id == other.id and self.name == other.name and self.d == other.d

    def __ne__(self, other):
        return not (self == other)
    
    def __getattr__(self, attr):
        if not Thing._reserved(attr) and self.d.has_key(attr):
            return self.d[attr]
        raise AttributeError, attr
        
    def __getitem__(self, attr):
        if not Thing._reserved(attr) and self.d.has_key(attr):
            return self.d[attr]
        raise KeyError, attr

    def get(self, key, default=None):
        return getattr(self, key, default)
    
    def __setattr__(self, attr, value):
        if Thing._reserved(attr):
            self.__dict__[attr] = value
            if attr == 'type':
                self._dirty = True
        else:
            self.d[attr] = value
            self._dirty = True
            
    __setitem__ = __setattr__
    
    def setdata(self, d):
        self.d = d
        self._dirty = True
            
    def save(self, comment='', author=None, ip=None):
        def savedatum(vid, key, value, ordering=None):
            if isinstance(value, str):
                dt = 0
            elif isinstance(value, Thing):
                dt = 1
                value = value.id
            elif isinstance(value, (int, long)):
                dt = 2
            elif isinstance(value, float):
                dt = 3
            else:
                raise BadData, value
            web.insert('datum', False, 
              version_id=vid, key=key, value=value, data_type=dt, ordering=ordering)
        

        if self._dirty is not True:
            return
        
        _run_hooks("before_new_version", self)
        web.transact()
        if self.id is None:
            tid = web.insert('thing', name=self.name, parent_id=self.parent.id, latest_revision=1)
            revision = 1
        else:
            tid = self.id
            result = web.query("SELECT revision FROM version \
                WHERE thing_id=$tid ORDER BY revision DESC LIMIT 1 \
                FOR UPDATE NOWAIT", vars=locals())
            revision = result[0].revision+1
            web.update('thing', where='id=$tid', latest_revision=revision, vars=locals())
            
        author_id = author and author.id
        vid = web.insert('version', thing_id=tid, comment=comment, 
            author_id=author_id, ip=ip, revision=revision)
        
        for k, v in self.d.items():
            if isinstance(v, list):
                for n, item in enumerate(v):
                    savedatum(vid, k, item, n)
            else:
                savedatum(vid, k, v)
        savedatum(vid, '__type__', self.type)
        
        logger.transact()
        try:
            if revision == 1:
                logger.log('thing', tid, name=self.name, parent_id=self.parent.id)
            logger.log('version', vid, thing_id=tid, author_id=author_id, ip=ip, 
                comment=comment, revision=revision)           
            logger.log('data', vid, __type__=self.type, **self.d)
            web.commit()
        except:
            logger.rollback()
            raise
        else:
            logger.commit()
        self.id = tid
        self.v = LazyVersion(vid)
        self.h = History(self.id)
        self.latest_revision = revision
        self._dirty = False
        _run_hooks("on_new_version", self)

class LazyThing(Thing):
    def __init__(self, id, revision=None):
        self.id = int(id)
        self._revision = revision

    def __getattr__(self, attr):
        if attr in ['id', '_revision']:
            return self.__dict__[attr]
        elif attr.startswith('__'):
            Thing.__getattr__(self, attr)
        else:
            args = withID(self.id, self._revision, raw=True)
            Thing.__init__(self, *args)
            self.__class__ = Thing
            return getattr(self, attr)
            
class Version:
    def __init__(self, id, thing_id, revision, author_id, ip, comment, created):
        web.autoassign(self, locals())
        self.thing = LazyThing(thing_id, revision)
        self.author = (author_id and LazyThing(author_id)) or None
    
    def __cmp__(self, other):
        return cmp(self.id, other.id)
        
    def __repr__(self): 
        return '<Version %s@%s at %s>' % (self.thing.id, self.revision, self.id)

class LazyVersion(Version):
    def __init__(self, id):
        self.id = int(id)
        
    def __getattr__(self, attr):
        if attr.startswith('__') or attr == 'id':
            Version.__getattr__(self, attr)
        else:
            v = web.select('version', where='id=$self.id', vars=locals())[0]
            Version.__init__(self, **v)
            self.__class__ = Version
            return getattr(self, attr)

def new(name, parent, type, d=None):
    if d == None: d = {}
    t = Thing(None, name, parent, type, d, None)
    t._dirty = True
    return t

def withID(id, revision=None, raw=False):
    try:
        t = web.select('thing', where="thing.id = $id", vars=locals())[0]
        revision = revision or t.latest_revision
        
        v = web.select('version',
            where='version.thing_id = $id AND version.revision = $revision', 
            vars=locals())[0]
        v = Version(**v)
        data = web.select('datum',
                where="version_id = $v.id", 
                order="key ASC, ordering ASC",
                vars=locals())
        d = {}
        for r in data:
            value = r.value
            if r.data_type == 0:
                pass # already a string
            elif r.data_type == 1:
                value = LazyThing(int(value))
            elif r.data_type == 2:
                value = int(value)
            elif r.data_type == 3:
                value = float(value)
            
            if r.ordering is not None:
                d.setdefault(r.key, []).append(value)
            else:
                d[r.key] = value
        
        type = d.pop('__type__')
        args = id, t.name, LazyThing(t.parent_id), type, d, v, t.latest_revision
        if raw:
            return args
        else:
            return Thing(*args)
    except IndexError:
        raise NotFound, id

def withName(name, parent, revision=None):
    try:
        id = web.select('thing', where='parent_id = $parent.id AND name = $name', vars=locals())[0].id
        return withID(id, revision)
    except IndexError:
        raise NotFound, name

class Things:
    def __init__(self, **query):
        tables = ['thing', 'version']
        what = 'thing.id'
        n = 0
        where = "thing.id = version.thing_id AND thing.latest_revision = version.revision"
        
        if 'parent' in query:
            parent = query.pop('parent')
            where += web.reparam(' AND thing.parent_id = $parent.id', locals())
        
        if 'type' in query:
            type = query.pop('type')
            query['__type__'] = type.id
        
        for k, v in query.items():
            n += 1
            if isinstance(v, Thing):
                v = v.id
            tables.append('datum AS d%s' % n)
            where += ' AND d%s.version_id = version.id AND ' % n + \
              web.reparam('d%s.key = $k AND d%s.value = $v' % (n, n), locals())
        
        self.values = [r.id for r in web.select(tables, what=what, where=where)]
        
    def __iter__(self):
        for item in self.values:
            yield withID(item)
    
    def list(self):
        return list(self)

class Versions:
    def __init__(self, **query):
        self.query = query
        self.versions = None
    
    def init(self):
        where = '1 = 1'
        for k, v in self.query.items():
            where += web.reparam(' AND %s = $v' % (k,), locals())
        self.versions = [Version(**v) for v in web.select('version', where=where, order='id desc')]
        
    def __getitem__(self, index):
        if self.versions is None:
            self.init()
        return self.versions[index]
    
    def __len__(self):
        if self.versions is None:
            self.init()
        return len(self.versions)
        
    def __str__(self):
        return str(self.versions)

class History(Versions):
    def __init__(self, thing_id):
        Versions.__init__(self, thing_id=thing_id)

# hooks can be registered by extending the hook class
hooks = []
class metahook(type):
    def __init__(self, name, bases, attrs):
        hooks.append(self())
        type.__init__(self, name, bases, attrs)
        
class hook:
    __metaclass__ = metahook

#remove hook from hooks    
hooks.pop()
        
def _run_hooks(name, thing):
    for h in hooks:
        m = getattr(h, name, None)
        if m:
            m(thing)
    
metatype = LazyThing(1)
usertype = LazyThing(2)

def setup():
    try:
        withID(1)
    except NotFound:
        # create metatype and user type
        new("metatype", metatype, metatype).save()
        new("user", metatype, metatype).save()

if __name__ == "__main__":
    import sys
    web.config.db_parameters = dict(dbn="postgres", db=sys.argv[1], user="anand", pw="anand123")
    web.load()
    setup()
