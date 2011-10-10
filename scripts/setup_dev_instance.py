#! /usr/bin/env python
"""Script to install OL dev instance.
"""

import ConfigParser
import os, shutil
import shlex
import subprocess
import sys
import time
import urllib, urllib2
import commands
import logging

logger = logging.getLogger("bootstrap")

VERSION = 7

CHANGELOG = """
001 - Initial setup
002 - Added couchdb and couchdb-lucene links in usr/local.
003 - Added iptools python module.
004 - Moved solr location
005 - Account v2
006 - Add extra couch design docs for tasks and support system
007 - Added loans design doc to admin database.
"""

config = None
INTERP = None

class Path:
    """Wrapper over file path, inspired by py.path.local.
    """
    def __init__(self, path):
        self.path = path
        
    def exists(self):
        return os.path.exists(self.path)
        
    def basename(self):
        return os.path.basename(self.path)
    
    def join(self, *a):
        parts = [self.path] + list(a)
        path = os.path.join(*parts)
        return Path(path)
        
    def mkdir(self, *parts):
        path = self.join(*parts).path
        if not os.path.exists(path):
            os.makedirs(path)
            
    def isdir(self):
        return os.path.isdir(self.path)
        
    def copy_to(self, dest, recursive=False):
        if isinstance(dest, Path):
            dest = dest.path
            
        options = ""
        if recursive:
            options += " -r"
            
        cmd = "cp %s %s %s" % (options, self.path, dest)
        os.system(cmd)
        
    def read(self):
        return open(self.path).read()
        
    def write(self, text, append=False):
        if append:
            f = open(self.path, 'a')
        else:
            f = open(self.path, 'w')
        f.write(text)
        f.close()

CWD = Path(os.getcwd())

## Common utilities
def log(level, args):
    msg = " ".join(map(str, args))
    if level == "ERROR" or level == "INFO":
        print msg

    text = time.asctime() + " " + level.ljust(6) + " " + msg + "\n"
    CWD.join("var/log/install.log").write(text, append=True)
    
def info(*args):
    log("INFO", args)
    
def debug(*args):
    log("DEBUG", args)
    
def error(*args):
    log("ERROR", args)
    
def write(path, text, append=False):
    if append:
        f = open(path, "a")
    else:
        f = open(path, "w")
    f.write(text)
    f.close()
    
def system(cmd):
    debug("Executing %r" % cmd)
    ret = os.system(">>var/log/install.log 2>&1 " + cmd)
    if ret != 0:
        raise Exception("%r failed with exit code %d" % (cmd, ret))

def setup_dirs():
    dirs = (
        "var/cache var/lib var/log var/run" +
        " var/lib/coverstore/localdisk" +
        " var/log/lighttpd var/cache/lighttpd/uploads var/www/cache " + 
        " usr/local/bin usr/local/etc usr/local/lib"
    )
    os.system("mkdir -p " + dirs)
    
    # this script is relaunched with python from virtualenv after setting up virtualenv.
    # install.log must not overwritten then.
    if os.getenv('OL_BOOTSTRAP_RELAUNCH') != "true":
        os.system("echo > var/log/install.log")

def read_config():
    """Reads conf/install.ini file.
    """
    info("reading config file config/install.ini")
    p = ConfigParser.ConfigParser()
    p.read("conf/install.ini")
    return dict(p.items("install"))
    
def download(url):
    path = CWD.join("var/cache", url.split("/")[-1])
    if not path.exists():
        system("wget %s -O %s" % (url, path.path))
    
def download_and_extract(url, dirname=None):
    download(url)

    path = CWD.join("var/cache", url.split("/")[-1])
    dirname = dirname or path.basename().replace(".tgz", "").replace(".tar.gz", "")
    if not CWD.join("usr/local", dirname).exists():
        system("cd usr/local && tar xzf " + path.path)

def find_distro():
    uname = os.uname()[0]
    if uname == "Darwin":
        return "osx"
    else:
        return "linux"
    
class Process:
    def __init__(self):
        self.process = None
        
    def start(self):
        info("    starting", self.__class__.__name__.lower())
        
        specs = self.get_specs()
        stdout = open("var/log/install.log", 'a')
        specs["stdout"] = stdout
        specs["stderr"] = stdout
        
        command = specs.pop("command")
        args = command.split()
        self.process = subprocess.Popen(args, **specs)
        self.wait_for_start()

    def wait_for_start(self):
        time.sleep(5)

    def wait_for_url(self, url):
        for i in range(10):
            try:
                urllib2.urlopen(url).read()
            except:
                time.sleep(0.5)
                continue
            else:
                return
        
    def stop(self):
        info("    stopping", self.__class__.__name__.lower())
        self.process and self.process.terminate()
        
    def run_tasks(self, *tasks):
        try:
            self.start()
            for task in tasks:
                task()
        finally:
            self.stop()
            
class Postgres(Process):
    def get_specs(self):
        return {
            "command": "usr/local/postgresql-8.4.4/bin/postgres -D var/lib/postgresql"
        }

class CouchDB(Process):
    def get_specs(self):
        return {
            "command": "usr/local/bin/couchdb",
        }

    def wait_for_start(self):
        self.wait_for_url("http://127.0.0.1:5984/")
        
    def create_database(self, name):
        import couchdb
        server = couchdb.Server("http://127.0.0.1:5984/")
        if name in server:
            debug("couchdb database already present: " + name)
        else:
            debug("creating couchdb database: " + name)
            server.create(name)
            
    def add_design_doc(self, dbname, path):
        """Adds a design document from the given path relative to couchapps/ direcotory to a couchdb database.
        """
        debug("adding design doc from %s to %s database" % (path, dbname))
        
        import couchdb
        server = couchdb.Server("http://127.0.0.1:5984/")
        db = server[dbname]
        
        from openlibrary.core.lists.tests.test_updater import read_couchapp
        design_doc = read_couchapp(path)
        id = design_doc['_id']
        if id in db:
            design_doc['_rev'] = db[id]['_rev']
        db[id] = design_doc
        db.commit()
    
class Infobase(Process):
    def get_specs(self):
        env = dict(os.environ, PYTHONPATH="conf", DISABLE_CELERY="true")
        return {
            "command": INTERP + " ./scripts/infobase-server conf/infobase.yml 7000",
            "env": env
        }

    def wait_for_start(self):
        self.wait_for_url("http://127.0.0.1:7000/")
        
    def get(self, path):
        try:
            response = urllib2.urlopen("http://127.0.0.1:7000/openlibrary.org" + path)
            return response.read()
        except urllib2.HTTPError, e:
            if e.getcode() == 404:
                return None
            else:
                raise
        
    def get_doc(self, key):
        import simplejson
        json = self.get("/get?key=" + key)
        return json and simplejson.loads(json)
        
    def post(self, path, data):   
        if isinstance(data, dict):
            data = urllib.urlencode(data)
        url = "http://127.0.0.1:7000/openlibrary.org" + path
        return urllib2.urlopen(url, data).read()

class OpenLibrary(Process):
    def get_specs(self):
        return {
            "command": INTERP + " ./scripts/openlibrary-server conf/openlibrary.yml --gunicorn -b 0.0.0.0:8080"
        }

    def wait_for_start(self):
        self.wait_for_url("http://127.0.0.1:8080/")

class DBTask:
    def getstatusoutput(self, cmd):
        debug("Executing", cmd)
        status, output = commands.getstatusoutput(cmd)
        debug(output)
        return status, output
        
    def has_database(self, name):
        status, output = self.getstatusoutput("psql %s -c 'select 1'" % name)
        return status == 0
        
    def has_table(self, db, column):
        status, output = self.getstatusoutput("psql %s -c '\d %s'" % (db, column))
        return status == 0
        
    def create_database(self, name):
        if self.has_database(name):
            debug("%s database is already present" % name)
        else:
            debug("creating %s database" % name)
            system("createdb " + name)

## Tasks

class setup_virtualenv:
    """Creates a new virtualenv and exec this script using python from that
    virtual env.
    """
    def run(self):
        if sys.executable != INTERP:
            pyenv = os.path.expanduser(config['virtualenv'])

            info("creating virtualenv at", pyenv)
            system("virtualenv " + pyenv + " --no-site-packages")
            
class install_python_dependencies:
    def run(self):
        # avoid installing the packages again after relaunch
        if os.getenv('OL_BOOTSTRAP_RELAUNCH') != "true":
            info("installing python dependencies")
            self.install_from_archive()
            info("  installing remaining packages")
            system(INTERP + " setup.py develop")
            
    def install_from_archive(self):
        # This list is maually created after uploading these files to ol_vendor item on archive.org.
        packages = """
        meld3       meld3-0.6.7.tar.gz
        pygments    Pygments-1.4.tar.gz
        jinja2      Jinja2-2.5.5.tar.gz
        docutils    docutils-0.7.tar.gz
        web         web.py-0.33.tar.gz
        
        babel       Babel-0.9.5.tar.gz
        Image       PIL-1.1.7.tar.gz
        simplejson  simplejson-2.1.3.tar.gz
        
        couchdb     CouchDB-0.8.tar.gz
        genshi      Genshi-0.6.tar.gz
        yaml        PyYAML-3.09.zip
        sphinx      Sphinx-1.0.7.tar.gz
        argparse    argparse-1.1.zip
        gunicorn    gunicorn-0.12.0.tar.gz
        lxml        lxml-2.3beta1.tar.gz
        psycopg2    psycopg2-2.3.2.tar.gz
        pymarc      pymarc-2.71.tar.gz
        py          py-1.4.0.zip
        py.test     pytest-2.0.0.zip
        memcache    python-memcached-1.47.tar.gz
        supervisor  supervisor-3.0a9.tar.gz
        """
        pyenv = os.path.expanduser(config['virtualenv'])
        tokens = packages.strip().split()
        for name, pkg in zip(tokens[::2], tokens[1::2]):
            try:
                __import__(name)
            except ImportError:
                url = "http://www.archive.org/download/ol_vendor/python-" + pkg
                info("  installing", url)
                download(url)
                system(pyenv + "/bin/easy_install -Z var/cache/python-" + pkg)

class switch_to_virtualenv:
    def run(self):
        if sys.executable != INTERP:
            pyenv = os.path.expanduser(config['virtualenv'])
            
            info("restarting the script with python from", INTERP)
            env = dict(os.environ)
            env['PATH'] = pyenv + "/bin:usr/local/bin:" + env['PATH']
            env['LD_LIBRARY_PATH'] = 'usr/local/lib'
            env['DYLD_LIBRARY_PATH'] = 'usr/local/lib'
            env['OL_BOOTSTRAP_RELAUNCH'] = "true"
            os.execvpe(INTERP, [INTERP] + sys.argv, env)
    
class install_solr:
    def run(self):
        info("installing solr...")
        download_and_extract("http://www.archive.org/download/ol_vendor/apache-solr-1.4.0.tgz")
        os.system("cd usr/local && ln -fs apache-solr-1.4.0 solr")


class install_couchdb_lucene:
    def run(self):    
        info("installing couchdb lucene...")
        download_and_extract("http://www.archive.org/download/ol_vendor/couchdb-lucene-0.6-SNAPSHOT-dist.tar.gz")
        os.system("cd usr/local/etc && ln -fs ../couchdb-lucene-0.6-SNAPSHOT/conf couchdb-lucene")
        self.setup_links()
        
    def setup_links(self):
        os.system("cd usr/local && ln -fs couchdb-lucene-0.6-SNAPSHOT couchdb-lucene")

class checkout_submodules:
    def run(self):
        info("checking out git submodules ...")
        system("git submodule init")
        system("git submodule update")
        
class update_submodules:
    def run(self):
        info("updating git submodules")
        system("git submodule update")

class install_couchdb:
    """Installs couchdb and updates configuration files..
    """
    def run(self):
        info("installing couchdb ...")
        distro = find_distro()
        if distro == "osx":
            self.install_osx()
        else:
            self.install_linux()
        self.setup_links()
        self.copy_config_files()    
            
    def install_osx(self):
        download_url = "http://www.archive.org/download/ol_vendor/couchdb-1.0.1-osx-binaries.tgz"
        
        download_and_extract(download_url, dirname="couchdb_1.0.1")
        # mac os x distribution uses relative paths. So no need to fix files.
        
    def install_linux(self):
        if self.is_64_bit():
            download_url = "http://www.archive.org/download/ol_vendor/couchdb-1.0.1-linux-64bit-binaries.tgz"
        else:
            download_url = "http://www.archive.org/download/ol_vendor/couchdb-1.0.1-linux-binaries.tgz"
        download_and_extract(download_url, dirname="couchdb-1.0.1")
        self.fix_linux_paths()
        
    def fix_linux_paths(self):
        root = CWD.join("usr/local/couchdb-1.0.1")
        DEFAULT_ROOT = "/home/anand/couchdb-1.0.1"
        
        for f in "bin/couchdb bin/couchjs bin/erl etc/couchdb/default.ini etc/init.d/couchdb etc/logrotate.d/couchdb lib/couchdb/erlang/lib/couch-1.0.1/ebin/couch.app".split():
            debug("fixing paths in", f)
            f = root.join(f)
            f.write(f.read().replace(DEFAULT_ROOT, root.path))
            
    def is_64_bit(self):
        return os.uname()[-1] == "x86_64"
        
    def setup_links(self):
        if find_distro() == "osx":
            os.system("cd usr/local/etc && ln -sf ../couchdb_1.0.1/etc/couchdb .")
            os.system("cd usr/local && ln -sf couchdb_1.0.1 couchdb")
        else:
            os.system("cd usr/local/bin && ln -fs ../couchdb-1.0.1/bin/couchdb .")
            os.system("cd usr/local/etc && ln -sf ../couchdb-1.0.1/etc/couchdb .")
            os.system("cd usr/local && ln -sf couchdb-1.0.1 couchdb")
    
    def copy_config_files(self):
        debug("copying config files")
        CWD.join("conf/couchdb/local.ini").copy_to("usr/local/etc/couchdb/")
        
class setup_coverstore(DBTask):
    """Creates and initialized coverstore db."""
    def run(self):
        info("setting up coverstore database")
        self.create_database("coverstore")
        
        if self.has_table("coverstore", "cover"):
            debug("schema is already loaded")
        else:
            debug("loading schema")
            system("psql coverstore < openlibrary/coverstore/schema.sql")
        
class setup_ol(DBTask):
    def run(self):
        info("setting up openlibrary database")
        self.create_database("openlibrary")
        
        Infobase().run_tasks(self.ol_install)
        self.create_ebook_count_db()
        
    def ol_install(self):
        info("    running OL setup script")
        system(INTERP + " ./scripts/openlibrary-server conf/openlibrary.yml install")
        
    def create_ebook_count_db(self):
        info("    setting up openlibrary_ebook_count database")
        self.create_database("openlibrary_ebook_count")
        
        schema = """
        create table subjects (
            field text not null,
            key character varying(255),
            publish_year integer, 
            ebook_count integer,
            PRIMARY KEY (field, key, publish_year)
        );
        CREATE INDEX field_key ON subjects(field, key);
        """
        
        if not self.has_table("openlibrary_ebook_count", "subjects"):
            import web
            db = web.database(dbn="postgres", db="openlibrary_ebook_count", user=os.getenv("USER"), pw="")
            db.printing = False
            db.query(schema)

class setup_couchdb:
    """Creates couchdb databases required for OL and adds design documents to them."""
    def run(self):
        info("setting up couchdb")
        self.couchdb = CouchDB()
        self.couchdb.run_tasks(self.create_dbs, self.add_design_docs)
        
    def create_dbs(self):
        info("    creating databases")
        self.couchdb.create_database("works")
        self.couchdb.create_database("editions")
        self.couchdb.create_database("seeds")
        self.couchdb.create_database("admin")
        
    def add_design_docs(self):
        info("    adding design docs")
        self.couchdb.add_design_doc("works", "works/seeds")
        self.couchdb.add_design_doc("editions", "editions/seeds")
        self.couchdb.add_design_doc("seeds", "seeds/dirty")
        self.couchdb.add_design_doc("seeds", "seeds/sort")
        self.couchdb.add_design_doc("celery", "celery/history")
        self.couchdb.add_design_doc("admin", "admin/cases")
        self.couchdb.add_design_doc("admin", "admin/loans")

class setup_accounts:
    """Task for creating openlibrary account and adding it to admin and api usergroups.
    """
    def run(self):
        info("setting up accounts...")
        self.infobase = Infobase()
        self.infobase.run_tasks(self.create_account, self.add_to_usergroups)
        
    def create_account(self):
        infobase = self.infobase
        if not infobase.get_doc("/people/openlibrary"):
            info("    creating openlibrary account")
            infobase.post("/account/register", {
                "username": "openlibrary",
                "password": "openlibrary",
                "email": "openlibrary@example.com",
                "displayname": "Open Library"
            })
        else:
            info("    openlibrary account is already present")
            
        debug("marking openlibrary as verified user...")
        infobase.post("/account/activate", {"username": "openlibrary"})
        
    def add_to_usergroups(self):
        infobase = self.infobase
        info("    adding openlibrary to admin and api usergroups")
        usergroups = [
            {
                "key": "/usergroup/api",
                "type": {"key": "/type/usergroup"},
                "members": [
                    {"key": "/people/admin"},
                    {"key": "/people/openlibrary"},
                ]
            }, 
            {
                "key": "/usergroup/admin",
                "type": {"key": "/type/usergroup"},
                "members": [
                    {"key": "/people/admin"},
                    {"key": "/people/openlibrary"},
                ]
            }
        ]
        import simplejson
        infobase.post("/save_many", {
            "query": simplejson.dumps(usergroups),
            "comment": "Added openlibrary to admin and api usergroups."
        })
        
class setup_globals:
    def run(self):
        global config
        config = read_config()
        
        global INTERP
        pyenv = os.path.expanduser(config['virtualenv'])
        INTERP = pyenv + "/bin/python"

cleanup_tasks = []

def register_cleanup(cleanup):
    cleanup_tasks.append(cleanup)
        
def install():
    setup_dirs()

    tasks = [
        setup_globals(),
        
        setup_virtualenv(),
        install_python_dependencies(),
        switch_to_virtualenv(),
        
        checkout_submodules(),
    
        install_couchdb(),
        install_solr(),
        install_couchdb_lucene(),
        
        setup_coverstore(),
        setup_ol(),
        setup_couchdb(),
        setup_accounts(),
    ]

    try:
        for task in tasks:
            task.run()
        
        update_current_version()
    finally:
        for cleanup in cleanup_tasks:
            cleanup()
            
def update():
    """Updates the existing dev instance to latest version.
    """
    tasks = [
        setup_globals(),
        switch_to_virtualenv(),
        update_submodules(),
        run_updates()
    ]
    
    for t in tasks:
        t.run()
    
class run_updates:
    def run(self):
        v = get_current_version()
        info("current version is", v)
        for f in get_update_functions(v):
            info("executing", f.__name__)
            f()
        update_current_version()
        info("latest version is", VERSION)

def get_update_functions(current_version):
    for i in range(current_version, VERSION):
        name = "update_%03d" % (i+1)
        yield globals()[name]

def update_002():
    """update the dev instance from version 1 to version 2."""
    install_couchdb().setup_links()
    install_couchdb_lucene().setup_links()

def update_003():
    install_python_dependencies().run()

def update_004():
    os.system("cd usr/local && mv solr solr_old")
    os.system("cd usr/local && ln -fs apache-solr-1.4.0 solr")
    os.mkdir('var/lib/solr')
    for i in ('authors', 'editions', 'inside', 'subjects', 'works'):
        os.mkdir('var/lib/solr/' + i)
        os.system("mv usr/local/solr_old/solr/" + i + "/data var/lib/solr/" + i) 
        
def update_005():
    import web
    from infogami.infobase._dbstore.store import Store
    
    db = web.database(dbn="postgres", db="openlibrary", user=os.getenv("USER"), pw="")    
    store = Store(db)
    
    for row in db.query("SELECT thing.key, thing.created, account.* FROM thing, account WHERE thing.id=account.thing_id"):
        username = row.key.split("/")[-1]
        account_key = "account/" + username
        
        if store.get(account_key):
            continue
        else:
            account = {
                "_key": account_key,
                "type": "account",
                "email": row.email,
                "enc_password": row.password,
                
                "username": username,
                "lusername": username.lower(),
                
                "bot": row.bot,
                "status": row.verified and "verified" or "pending",
                "created_on": row.created.isoformat(),
            }
            email_doc = {
                "_key": "account-email/" + row.email,
                "type": "account-email",
                "username": username
            }
            store.put_many([account, email_doc])

def update_006():
    couchdb = CouchDB()
    def update_design_docs(couchdb = couchdb):
        couchdb.create_database("celery")
        couchdb.add_design_doc("celery", "celery/history")
        couchdb.add_design_doc("admin", "admin/cases")
    couchdb.run_tasks(update_design_docs)

def update_007():
    couchdb = CouchDB()
    def update_design_docs(couchdb = couchdb):
        couchdb.add_design_doc("admin", "admin/loans")
    couchdb.run_tasks(update_design_docs)


def get_current_version():
    """Returns the current version of dev instance.
    """
    return int(read_system_config().get("system", "version"))
    
def read_system_config():
    p = ConfigParser.ConfigParser()
    p.read(["var/run/system.conf"])
    
    if not p.has_section("system"):
        p.add_section("system")
    
    if not p.has_option("system", "version"):
        p.set("system", "version", "1")
    
    return p
    
def update_current_version():
    p = read_system_config()
    p.set("system", "version", VERSION)
    
    f = open("var/run/system.conf", 'w')
    p.write(f)
    f.close()
    
def setup_logger():
    formatter = logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
    
    h1 = logging.StreamHandler()
    h1.setLevel(logging.INFO)
    h1.setFormatter(formatter)

    stderr = open("var/log/install.log", "a")
    sys.stderr = stderr
    
    h2 = logger.StreamHandler(stderr)
    h2.setLevel(logging.DEBUG)
    h2.setFormatter(formatter)
    
    logger.addHandler(h1)
    logger.addHandler(h2)
    
    logger.info("Welcome")
    logger.debug("debug")
    
if __name__ == '__main__':
    #setup_logger()
    
    if "--update" in sys.argv:
        update()
    else:
        install()
