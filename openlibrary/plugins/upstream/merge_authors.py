"""Merge authors.
"""
import web, re
import simplejson
from infogami.utils import delegate
from infogami.utils.view import render_template, safeint

from openlibrary.plugins.worksearch.code import top_books_from_author

class BasicMergeEngine:
    """Generic merge functionality useful for all types of merges.
    """
    def merge(self, master, duplicates):
        docs = self.do_merge(master, duplicates)
        return self.save(docs, master, duplicates)
        
    def do_merge(self, master, duplicates):
        """Performs the merge and returns the list of docs to save.
        """
        docs_to_save = []
        
        # mark all the duplcates as redirects to the master
        docs_to_save.extend(self.make_redirect_doc(key, master) for key in duplicates)
        
        # find the references of each duplicate and covert them
        references = self.find_all_backreferences(duplicates)
        docs = self.get_many(references)
        docs_to_save.extend(self.convert_doc(doc, master, duplicates) for doc in docs)
        
        # finally, merge all the duplicates into the master.
        master_doc = web.ctx.site.get(master).dict()
        dups = self.get_many(duplicates)
        for d in dups:
            master_doc = self.merge_docs(master_doc, d)
            
        docs_to_save.append(master_doc)
        return docs_to_save
        
    def get_many(self, keys):
        def process(doc):
            # some books have bad table_of_contents. Fix them to avoid failure on save.
            if doc['type']['key'] == "/type/edition":
                if 'table_of_contents' in doc:
                    doc['table_of_contents'] = fix_table_of_contents(doc['table_of_contents'])
            return doc
        return [process(thing.dict()) for thing in web.ctx.site.get_many(list(keys))]
        
    def find_all_backreferences(self, duplicates):
        references = set()
        for key in duplicates:
            references.update(self.find_backreferences(key))
        return list(references)

    def find_backreferences(self, key):
        """Returns keys of all the docs which have a reference to the given key.

        All the subclasses must provide an implementation for this method.
        """
        raise NotImplementedError()
        
    def save(self, docs, master, duplicates):
        """Saves the effected docs because of merge.
        
        All the subclasses must provide an implementation for this method.
        """
        raise NotImplementedError()
            
    def merge_docs(self, master, dup, ignore=[]):
        """Merge duplicate doc into master doc.
        """
        keys = set(master.keys() + dup.keys())
        return dict((k, self.merge_property(master.get(k), dup.get(k))) for k in keys)
        
    def merge_property(self, a, b):
        if isinstance(a, list) and isinstance(b, list):
            return uniq(a + b, key=dicthash)
        elif not a:
            return b
        else:
            return a
        
    def make_redirect_doc(self, key, redirect):
        return {
            "key": key,
            "type": {"key": "/type/redirect"},
            "location": redirect
        }
    
    def convert_doc(self, doc, master, duplicates):
        """Converts references to any of the duplicates in the given doc to the master.
        """
        if isinstance(doc, dict):
            if len(doc) == 1 and doc.keys() == ['key']:
                key = doc['key']
                if key in duplicates:
                    return {"key": master}
                else:
                    return doc
            else:
                return dict((k, self.convert_doc(v, master, duplicates)) for k, v in doc.iteritems())
        elif isinstance(doc, list):
            values = [self.convert_doc(v, master, duplicates) for v in doc]
            return uniq(values, key=dicthash)
        else:
            return doc

class AuthorMergeEngine(BasicMergeEngine):
    def merge_docs(self, master, dup):
        # avoid merging other types.
        if dup['type']['key'] == '/type/author':
            master = BasicMergeEngine.merge_docs(self, master, dup)
            if dup.get('name') and not name_eq(dup['name'], master.get('name') or ''):
                master.setdefault('alternate_names', []).append(dup['name'])
            if 'alternate_names' in master:
                master['alternate_names'] = uniq(master['alternate_names'], key=space_squash_and_strip)
        return master
        
    def save(self, docs, master, duplicates):
        data = {
            "master": master,
            "duplicates": list(duplicates)
        }
        
        # There is a bug (#89) due to which old revisions of the docs are being sent to save.
        # Collecting all the possible information to detect the problem and saving it in datastore.
        debug_doc = {}
        debug_doc['type'] = 'merge-authors-debug' 
        mc = self._get_memcache()
        debug_doc['memcache'] = mc and dict((k, simplejson.loads(v)) for k, v in mc.get_multi([doc['key'] for doc in docs]).items())
        debug_doc['docs'] = docs
        
        result = web.ctx.site.save_many(docs, comment='merge authors', action="merge-authors", data=data)
        
        docrevs= dict((doc['key'], doc.get('revision')) for doc in docs)
        revs = dict((row['key'], row['revision']) for row in result)
        
        # Bad merges are happening when we are getting non-recent docs.
        # That can be identified by checking difference in the revision numbers before and after save
        bad_merge = any(revs[k]-docrevs[k] > 1 for k in revs if docrevs[k] is not None)
        
        debug_doc['bad_merge'] = str(bad_merge).lower()
        debug_doc['result'] = result
        key = 'merge_authors/%d' % web.ctx.site.seq.next_value('merge-authors-debug')
        web.ctx.site.store[key] = debug_doc
        
        return result
        
    def _get_memcache(self):
        from openlibrary.plugins.openlibrary import connection
        return connection._memcache
    
    def find_backreferences(self, key):
        q = {
            "type": "/type/edition",
            "authors": key,
            "limit": 10000
        }
        edition_keys = web.ctx.site.things(q)
        
        editions = self.get_many(edition_keys)
        work_keys_1 = [w['key'] for e in editions for w in e.get('works', [])]

        q = {
            "type": "/type/work",
            "authors": {"author": {"key": key}},
            "limit": 10000
        }
        work_keys_2 = web.ctx.site.things(q)
        return edition_keys + work_keys_1 + work_keys_2

re_whitespace = re.compile('\s+')
def space_squash_and_strip(s):
    return re_whitespace.sub(' ', s).strip()

def name_eq(n1, n2):
    return space_squash_and_strip(n1) == space_squash_and_strip(n2)
    
def uniq(values, key=None):
    """Returns the unique entries from the given values in the original order.
    
    The value of the optional `key` parameter should be a function that takes
    a single argument and returns a key to test the uniqueness.
    """
    key = key or (lambda x: x)
    s = set()
    result = []
    for v in values:
        k = key(v)
        if k not in s:
            s.add(k)
            result.append(v)
    return result
    
def dicthash(d):
    """Dictionaries are not hashable. This function converts dictionary into nested tuples, so that it can hashed.
    """
    if isinstance(d, dict):
        return tuple((k, dicthash(v)) for k, v in d.iteritems())
    elif isinstance(d, list):
        return tuple(dicthash(v) for v in d)
    else:
        return d
        
def fix_table_of_contents(table_of_contents):
    """Some books have bad table_of_contents. This function converts them in to correct format.
    """
    def row(r):
        if isinstance(r, basestring):
            level = 0
            label = ""
            title = web.safeunicode(r)
            pagenum = ""
        elif 'value' in r:
            level = 0
            label = ""
            title = web.safeunicode(r['value'])
            pagenum = ""            
        else:
            level = safeint(r.get('level', '0'), 0)
            label = r.get('label', '')
            title = r.get('title', '')
            pagenum = r.get('pagenum', '')
            
        r = web.storage(level=level, label=label, title=title, pagenum=pagenum)
        return r
    
    d = [row(r) for r in table_of_contents]
    return [row for row in d if any(row.values())]

class merge_authors(delegate.page):
    path = '/authors/merge'

    def is_enabled(self):
        return "merge-authors" in web.ctx.features
        
    def filter_authors(self, keys):
        docs = web.ctx.site.get_many(["/authors/" + k for k in keys])
        d = dict((doc.key, doc.type.key) for doc in docs)
        return [k for k in keys if d.get("/authors/" + k) == '/type/author']

    def GET(self):
        i = web.input(key=[])
        keys = uniq(i.key)
        
        # filter bad keys
        keys = self.filter_authors(keys)
        return render_template('merge/authors', keys, top_books_from_author=top_books_from_author)

    def POST(self):
        i = web.input(key=[], master=None, merge_key=[])
        keys = uniq(i.key)
        selected = uniq(i.merge_key)
        
        # filter bad keys
        keys = self.filter_authors(keys)        

        # doesn't make sense to merge master with it self.
        if i.master in selected:
            selected.remove(i.master)

        formdata = web.storage(
            master=i.master, 
            selected=selected
        )

        if not i.master or len(selected) == 0:
            return render_template("merge/authors", keys, top_books_from_author=top_books_from_author, formdata=formdata)
        else:                
            # redirect to the master. The master will display a progressbar and call the merge_authors_json to trigger the merge.
            master = web.ctx.site.get("/authors/" + i.master)
            raise web.seeother(master.url() + "?merge=true&duplicates=" + ",".join(selected))

class merge_authors_json(delegate.page):
    """JSON API for merge authors. 

    This is called from the master author page to trigger the merge while displaying progress.
    """
    path = "/authors/merge"
    encoding = "json"

    def is_enabled(self):
        return "merge-authors" in web.ctx.features

    def POST(self):
        json = web.data()
        data = simplejson.loads(json)
        master = data['master']
        duplicates = data['duplicates']
        
        engine = AuthorMergeEngine()
        result = engine.merge(master, duplicates)
        return delegate.RawText(simplejson.dumps(result),  content_type="application/json")

def setup():
    pass
