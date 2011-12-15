"""Special customizations for dev instance.

This module is imported only if dev_instance is set to True in openlibrary config.
"""
import web
import infogami
from infogami.utils import delegate
from openlibrary.core.task import oltask
from openlibrary.tasks import other_on_edit_tasks

def setup():
    setup_solr_updater()
    
    # Run update_solr on every edit
    other_on_edit_tasks.append(update_solr)
        
    from openlibrary.catalog.utils import query
    # monkey-patch query to make solr-updater work with-in the process instead of making http requests.
    query.query = ol_query
    query.withKey = ol_get

def ol_query(q):
    return web.ctx.site.things(q, details=True)

def ol_get(key):
    d = web.ctx.site.get(key)
    return d and d.dict()

def setup_solr_updater():
    from infogami import config
    
    # solr-updater reads configuration from openlibrary.config.runtime_config
    from openlibrary import config as olconfig
    olconfig.runtime_config = config.__dict__
    
    # The solr-updater makes a http call to the website insted of using the 
    # infobase API. It requires setting the host before start using it.
    from openlibrary.catalog.utils.query import set_query_host
    
    dev_instance_url = config.get("dev_instance_url", "http://127.0.0.1:8080/")
    host = web.lstrips(dev_instance_url, "http://").strip("/")
    set_query_host(host)

class is_loaned_out(delegate.page):
    path = "/is_loaned_out/.*"
    def GET(self):
        return delegate.RawText("[]", content_type="application/json")

class process_ebooks(delegate.page):
    """Hack to add ebooks to store so that books are visible in the returncart.
    """
    path = "/_dev/process_ebooks"
    
    def GET(self):
        from openlibrary.plugins.worksearch.search import get_works_solr
        result = get_works_solr().select(query='borrowed_b:false', fields=['key', 'lending_edition_s'], limit=100)
        
        def make_doc(d):
            # Makes a store doc from solr doc
            return {
                "_key": "ebooks/books/" + d['lending_edition_s'],
                "_rev": None, # Don't worry about consistancy
                "type": "ebook",
                "book_key": "/books/" + d['lending_edition_s'],
                "borrowed": "false"
            }
        
        docs = [make_doc(d) for d in result['docs']]
        docdict = dict((d['_key'], d) for d in docs)
        web.ctx.site.store.update(docdict)
        return delegate.RawText("ok\n")

@oltask
def update_solr(changeset):
    """Updates solr on edit.
    """
    from openlibrary.solr import update_work
    
    keys = set()
    docs = changeset['docs'] + changeset['old_docs']
    docs = [doc for doc in docs if doc] # doc can be None if it is newly created.
    for doc in docs:
        if doc['type']['key'] == '/type/edition':
            keys.update(w['key'] for w in doc.get('works', []))
        elif doc['type']['key'] == '/type/work':
            keys.add(doc['key'])
            keys.update(a['author']['key'] for a in doc.get('authors', []) if 'author' in a)
        elif doc['type']['key'] == '/type/author':
            keys.add(doc['key'])
            
    update_work.update_keys(list(keys))
    
@infogami.install_hook
def add_ol_user():
    """Creates openlibrary user with admin previleges.
    """
    # Create openlibrary user
    if web.ctx.site.get("/people/openlibrary") is None:
        web.ctx.site.register(
            username="openlibrary",
            email="openlibrary@example.com",
            password="openlibrary",
            displayname="Open Library")
        web.ctx.site.activate_account(username="openlibrary")
        
    if web.ctx.site.get("/usergroup/api") is None:
        g_api = web.ctx.site.new("/usergroup/api", {
            "key": "/usergroup/api",
            "type": "/type/usergroup",
            "members": [{"key": "/people/openlibrary"}]
        })
        g_api._save(comment="Added openlibrary user to API usergroup.")
        
    g_admin = web.ctx.site.get("/usergroup/admin").dict()
    g_admin.setdefault('members', [])
    members = [m['key'] for m in g_admin["members"]]
    if 'openlibrary' not in members:
        g_admin['members'].append({"key": "/people/openlibrary"})
        web.ctx.site.save(g_admin, "Added openlibrary user to admin usergroup.")

@infogami.action
def load_sample_data():
    """Action to load sample data.

    This was an experiment to load sample data as part of install. But it
    doesn't seem to be working well on linux dev-instance because of some weird
    supervisor log issues.

    This is unused as of now.
    """
    env = {}
    execfile("scripts/copydocs.py", env, env)
    src = env['OpenLibrary']()
    dest = web.ctx.site
    comment = "Loaded sample data."
    list_key = "/people/anand/lists/OL1815L"
    env['copy_list'](src, dest, list_key, comment=comment)
