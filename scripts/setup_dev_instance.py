#! /usr/bin/env python
"""Script to install OL dev instance.
"""

import ConfigParser
import os
import sys
import time
import commands
import logging
import urllib2
import subprocess

logger = logging.getLogger("bootstrap")

VERSION = 9

CHANGELOG = """
001 - Initial setup
002 - Added couchdb and couchdb-lucene links in usr/local.
003 - Added iptools python module.
004 - Moved solr location
005 - Account v2
006 - Add extra couch design docs for tasks and support system
007 - Added loans design doc to admin database.
008 - Install OL-GeoIP package
009 - Simplified dev instance
"""

config = None
INTERP = sys.executable

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
        " usr/local/bin usr/local/etc usr/local/lib"
    )
    os.system("mkdir -p " + dirs)

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

class OpenLibrary(Process):
    def get_specs(self):
        return {
            #"command": INTERP + " ./scripts/openlibrary-server conf/openlibrary.yml startserver 0.0.0.0:8080"
            "command":  "env/bin/supervisord -n -c conf/services.ini"
        }

    def wait_for_start(self):
        self.wait_for_url("http://127.0.0.1:8080/")
        
class Solr(Process):
    def get_specs(self):
        return {
            "command": "cd usr/local/solr/example && java -Dsolr.solr.home=../../../../conf/solr-biblio -Dsolr.data.dir=../../../../var/lib/solr -jar start.jar"
        }

    def wait_for_start(self):
        self.wait_for_url("http://127.0.0.1:9883/")

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

class install_solr:
    def run(self):
        info("installing solr...")
        download_and_extract("http://www.archive.org/download/ol_vendor/apache-solr-1.4.0.tgz")
        os.system("cd usr/local && ln -fs apache-solr-1.4.0 solr")
        
class update_submodules:
    def run(self):
        info("updating git submodules")
        system("git submodule update")
        
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
        system(INTERP + " ./scripts/openlibrary-server conf/openlibrary.yml install")

class load_sample_data:
    def run(self):
        info("loading sample data")
        OpenLibrary().run_tasks(self.load)
    
    def load(self):
        # load docs from a list
        system(INTERP + " ./scripts/copydocs.py --list /people/anand/lists/OL1815L")
        
        # Hack to load borrowable ebooks to store so that they appear in the return cart
        urllib2.urlopen("http://0.0.0.0:8080/_dev/process_ebooks").read()
        
cleanup_tasks = []

def register_cleanup(cleanup):
    cleanup_tasks.append(cleanup)
        
def install():
    setup_dirs()

    tasks = [
        install_solr(),
        setup_coverstore(),
        setup_ol(),
        
        #XXX: This is not working linux due to some weird issues. Taking it off for now.
        #load_sample_data()
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
    run_updates()
    
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
    # couchdb is obsolete now
    pass
    
def update_003():
    # python dependencies are installed by make before calling this script
    pass
    
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
    # CouchDB is obsolete now
    pass

def update_007():
    # CouchDB is obsolete now
    pass

def update_008():
    # installing GeoIP is now taken care by setup.py/requirements.txt
    pass

def update_009():
    pass


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
