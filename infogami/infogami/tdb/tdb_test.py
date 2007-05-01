import random
import web
import tdb
import unittest

testtype = None

def simplething(name):
    t = tdb.new(name, testtype, testtype, {'title' : name})
    t.save('saving ' + name);
    return t
    
def setup():
    web.config.db_parameters = dict(dbn='postgres', db='tdbtest', user='postgres', pw='')
    web.db._hasPooling = False
    web.config.db_printing = False
    web.load()
    tdb.setup()
    
    # clear the database
    web.query('delete from datum where version_id > 2')
    web.query('delete from version where thing_id > 2')
    web.query('delete from thing where id > 2')
    
    global testtype
    testtype = tdb.new('test', tdb.metatype, tdb.metatype)
    testtype.save()
    
    simplething('test1')
    simplething('test2')
    simplething('test3')

def new(name, parent=None, type=None, d=None):
    if d is None: d = {}    
    return tdb.new(name, parent or testtype, type or testtype, d)

class tdbtest(unittest.TestCase):
    def test_new(self):
        t = new('foo', d={'title': 'Foo', 'body': "Baz biz boz."})
        assert t.name == 'foo' 
        assert t.title == "Foo"
        
        t.title = "The Story of Foo"
        assert t.title == "The Story of Foo"
        assert t.d['title'] == "The Story of Foo"
        assert t._dirty
        
        t.save('test cases')
        assert not t._dirty
        assert t.id

        t.title = 'foofoo'
        assert t._dirty

    def test_eq(self):
        t1 = simplething('eq1')
        t2 = tdb.withID(t1.id)
        assert t1 == t2

        t1.name = 'eq2'
        assert t1 != t2

    def test_with(self):
        t = new('withid', d={'title' : 'foo', 'body':'bar'})
        t.save('')
        
        assert t == tdb.withID(t.id)
        assert t == tdb.withName(t.name, testtype)
        assert tdb.withID(t.id) == tdb.withName(t.name, testtype)

    def test_list(self):
        subjects = ['Foo', 'Stories']
        authors = ['Joe Jacobson']
        test1 = tdb.withName('test1', testtype)

        t = new('list')
        t.subjects = subjects
        t.authors = authors
        assert t.subjects == subjects
        assert t.authors == authors

        t.related = [test1]
        t.save('test list')

        t = tdb.withID(t.id)
        t.subjects == subjects
        t.authors == authors
        assert test1.id in [x.id for x in t.related]

    def test_repr(self):
        t = tdb.withName('test1', testtype)
        t.id = 1
        t.name = 'foo'
        assert repr(t) == '<Thing "foo" at 1>'

    def test_things(self):
        x = tdb.withName('test1', testtype)
        tl = tdb.Things(title='test1').list()
        assert tl == [x]

        y = new('test11', d={'title' : 'test1', 'body' : 'a'})
        y.save('y')
        z = new('test11', parent=y, d={'title' : 'test1', 'body' : 'a'})
        z.save('z')

        tl = tdb.Things(title='test1').list()
        assert tl == [x, y, z]
        
        tl = tdb.Things(title='test1', body='a').list()
        assert tl == [y, z]
        
        tl = tdb.Things(title='notitle').list()
        assert tl == []        
        
    def test_LazyThing(self):
        a = tdb.LazyThing(1)
        assert a
        assert a is a
        assert a == tdb.metatype

        a = tdb.LazyThing(1)
        assert a.__class__ == tdb.LazyThing
        a.name # access name
        assert a.__class__ == tdb.Thing

        a = tdb.LazyThing(1)
        a.id # access id
        assert a.__class__ == tdb.LazyThing        

    def test_parent(self):
        a = new('parent', d={'title' : 'parent'})
        a.save('save parent')
        assert a.parent == testtype

        b = new('child', parent=a, d={'title' : 'child'})
        assert b.parent == a
        b.save('save child')

        b = tdb.withID(b.id)
        assert b.parent == a
        
        # it should be possible to create 2 things with same name, but different parents
        x = new('cat', parent=a)
        x.save('')
        y = new('cat', parent=b)
        y.save('')        
        assert x.name == y.name
        
    def assertException(self, exc, f, *a, **kw):
        try:
            f(*a, **kw)
        except exc:
            pass
        else:
            raise Exception, "%s should be raised" % (exc)
    
    def testExceptions(self):
        t1 = tdb.withName('test1', testtype)
        # NotFound is raised when thing is not found
        self.assertException(tdb.NotFound, tdb.withID, t1.id+1000)
        self.assertException(tdb.NotFound, tdb.withName, 'nothing', testtype)
        
        # AttributeError is raised when attr is not available
        self.assertException(AttributeError, getattr, t1, 'nothing')
        
        # database exception is raised when you try to create a thing with duplicate name
        self.assertException(Exception, new('test1').save)
    
    def testVersion(self):
        aaron = new('aaron', parent=tdb.usertype, type=tdb.usertype, d={'email': 'aaron@tdb.org'})
        aaron.save()
        anand = new('anand', parent=tdb.usertype, type=tdb.usertype, d={'email': 'anand@tdb.org'})
        anand.save()

        t = new('tdb', d={'title' : 'tdb v1'})
        t.save(comment='first draft', ip='1.2.3.4', author=aaron)
        assert t.v.thing == t
        assert t.v.comment == 'first draft'
        assert t.v.ip == '1.2.3.4'
        assert t.v.revision == 1
        assert t.latest_revision == 1
        assert t.v.author == aaron
        assert list(t.h) == [t.v]
        v1 = t.v

        t.title = 'tdb v2'
        t.save(comment='second draft', author=anand)
        assert t.v.thing == t
        assert t.v.ip == None
        assert t.v.comment == 'second draft'
        assert t.v.revision == 2
        assert t.latest_revision == 2    
        assert t.v.author == anand
        assert list(t.h) == [t.v, v1]
        
        assert v1.thing.title == 'tdb v1'
        assert t.h[0].thing == t
        assert t.h[1].thing == tdb.withID(t.id, revision=1)
    
    def testType(self):
        a = new('typetest')
        a.save()
        
        assert a.type == testtype
        
        a = tdb.withName('typetest', testtype)
        assert a.type == testtype
        
        # change type        
        a.type = tdb.usertype
        assert a.type == tdb.usertype
        assert a._dirty
        a.save()
        assert a.v.revision == 2
        
        assert a.h[0].thing.type == tdb.usertype
        assert a.h[1].thing.type == testtype

        # change type_id
        a.type = tdb.metatype
        assert a.type == tdb.metatype
        a.save()
        
        assert a.h[0].thing.type == tdb.metatype
        assert a.h[1].thing.type == tdb.usertype
        assert a.h[2].thing.type == testtype
                
if __name__ == "__main__":
    setup()
    unittest.main()
    #tdbtest().testVersion()