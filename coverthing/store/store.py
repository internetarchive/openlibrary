"""
Object store.
"""
import re
import web
from disk import File

class BadData(Exception): pass

TYPE_STRING = 1
TYPE_FILE = 10

re_key = re.compile("[A-Za-z_][A-Za-z0-9_]*")
def validate_key(name):
    if not re_key.match(name):
        raise BadData, 'Invalid key: ' + name 

class Store:
    def __init__(self, disk):
        self.disk = disk

    def save(self, object):
        """Saves the data and returns its object id"""
        for k, v in object.items():
            validate_key(k)

        #@@ what will happen to this row if subsequent operations fail?
        id = web.insert('thing', dummy=1)
        headers = dict((k, v) for k, v in object.items() if not isinstance(v, File))
        values = {}

        for k, v in object.items():
            if isinstance(v, File):
                filename = self.disk.write('%d.%s' % (id, k), v)
                values[k] = (filename, TYPE_FILE)
            else:
                values[k] = (v, self._gettype(v))

        web.transact()
        for k, (v, datatype) in values.items():
            web.insert('datum', False, thing_id=id, key=k, value=v, datatype=datatype)
        web.commit()

        return id

    def _gettype(self, value):
        if isinstance(value, basestring):
            return TYPE_STRING
        elif isinstance(value, File):
            return TYPE_FILE
        else:
            raise BadData, value
        
    def get(self, id, what=None):
        q = web.reparam('SELECT * FROM datum WHERE thing_id=$id', locals())
        if what is not None:
            q += ' AND ' + web.sqlors('key = ', what)
    
        result = list(web.query(q))
        d = {}
        for row in result:
            key, value, datatype = row.key, row.value, row.datatype
            if datatype == TYPE_FILE:
                value = self.disk.read(value)
            d[key] = value
        return d

    def query(self, query, limit=None, offset=None):
        """Queries the database for objetcs having matching properties 
        specified in the query and returns their ids. 
        Optional limit can be specified to limit the number of objects.
        """ 
        what = 'thing.id'
        tables = ['thing']
        
        where = '1 = 1'
        n = 0
        vars = {}
        for k, v in query.items():
            n += 1
            tables.append('datum AS d%d' % n)
            where += web.reparam(' AND thing.id = d%d.thing_id AND d%d.key = $k AND d%d.value = $v' % (n, n, n), locals())

        return [r.id for r in web.select(tables, what=what, where=where, limit=limit, offset=offset)]
