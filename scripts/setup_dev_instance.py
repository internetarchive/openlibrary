#! /usr/bin/env python
"""Script to install OL dev instance.
"""
import ConfigParser
import os
import shlex
import subprocess
import sys
import time
import urllib, urllib2
import commands

config = None
INTERP = None

CWD = os.getcwd()

## Common utilities
def log(level, args):
    msg = " ".join(map(str, args))
    if level == "ERROR" or level == "INFO":
        print msg

    text = time.asctime() + " " + level.ljust(6) + " " + msg + "\n"
    write(CWD + "/var/log/install.log", text, append=True)
    
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
    os.system("mkdir -p var/lib var/run var/log")
    os.system("echo > var/log/install.log")

def read_config():
    """Reads conf/install.ini file.
    """
    info("reading config file config/install.ini")
    p = ConfigParser.ConfigParser()
    p.read("conf/install.ini")
    return dict(p.items("install"))
    
def wget(url):
    filename = "vendor/" + url.split("/")[-1]
    if not os.path.exists(filename):
        system("wget %s -O %s" % (url, filename))
    return filename

def download_and_extract(url, dirname=None):
    filename = "vendor/" + url.split("/")[-1]
    if not os.path.exists(filename):
        system("wget %s -O %s" % (url, filename))

    dirname = dirname or filename.replace(".tgz", "").replace(".tar.gz", "")
    if not os.path.exists(dirname):
        system("cd vendor && tar xzf " + os.path.basename(filename))
    
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
        time.sleep(2)
        
    def stop(self):
        info("    stopping", self.__class__.__name__.lower())
        self.process and self.process.terminate()
        
    def run_tasks(self, *tasks):
        try:
            self.start()
            for task in tasks:
                task(self)
        finally:
            self.stop()
                        
class CouchDB(Process):
    def get_specs(self):
        return {
            "command": "bin/couchdb",
            "cwd": "vendor/couchdb-1.0.1"
        }
        
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
        return {
            "command": INTERP + " ./scripts/infobase-server conf/infobase.yml 7500"
        }
        
    def get(self, path):
        try:
            response = urllib2.urlopen("http://127.0.0.1:7500/openlibrary.org" + path)
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
        return urllib2.urlopen("http://127.0.0.1:7500/openlibrary.org" + path, data).read()
        
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
        global INTERP
    
        pyenv = os.path.expanduser(config['virtualenv'])
        INTERP = pyenv + "/bin/python"
    
        if sys.executable != INTERP:
            info("creating virtualenv at", pyenv)
            system("virtualenv " + pyenv)
        
            info("restarting the script with python from", INTERP)
            env = dict(os.environ)
            env['PATH'] = pyenv + "/bin:" + env['PATH']
            os.execvpe(INTERP, [INTERP] + sys.argv, env)
        
class install_python_dependencies:
    def run(self):
        info("installing python dependencies")
        system(INTERP + " setup.py develop")
    
class install_solr:
    def run(self):
        info("installing solr...")
    
        download_and_extract("http://www.archive.org/download/ol_vendor/apache-solr-1.4.0.tgz")
    
        types = 'authors', 'editions', 'works', 'subjects', 'inside'
        paths = ["vendor/solr/solr/" + t for t in types] 
        system("mkdir -p " + " ".join(paths))
    
        for f in "etc lib logs webapps start.jar".split():
            system("cp -R vendor/apache-solr-1.4.0/example/%s vendor/solr/" % f)
    
        system("cp conf/solr-biblio/solr.xml vendor/solr/solr/")

        solrconfig = open("vendor/apache-solr-1.4.0/example/solr/conf/solrconfig.xml").read()
    
        for t in types:
            if not os.path.exists('solr/solr/' + t + '/conf'):
                system("cp -r vendor/apache-solr-1.4.0/example/solr/conf vendor/solr/solr/%s/conf" % t)
            
            system('cp conf/solr-biblio/%s.xml vendor/solr/solr/%s/conf/schema.xml' % (t, t))
        
            f = 'vendor/solr/solr/' + t + '/conf/solrconfig.xml'
            debug("creating", f)
            write(f, solrconfig.replace("./solr/data", "./solr/%s/data" % t))

class install_couchdb_lucene:
    def run(self):    
        info("installing couchdb lucene...")
        download_and_extract("http://www.archive.org/download/ol_vendor/couchdb-lucene-0.6-SNAPSHOT-dist.tar.gz")    

class checkout_submodules:
    def run(self):
        info("checking out git submodules ...")
        system("git submodule init")
        system("git submodule update")

class install_couchdb:
    """Installs couchdb and updates configuration files..
    """
    def run(self):
        distro = self.find_distro()
        if distro == "osx":
            self.install_osx()
        else:
            self.install_linux()
        self.copy_config_files()    
            
    def copy_config_files(self):
        debug("copying config files")
        system("cp conf/couchdb/local.ini vendor/couchdb-1.0.1/etc/couchdb/")
        
    def install_osx(self):
        pass
        
    def install_linux(self):
        download_url = "http://www.archive.org/download/ol_vendor/couchdb-1.0.1-linux-binaries.tgz"
        download_and_extract(download_url, dirname="couchdb-1.0.1")
        self.fix_linux_paths()
        
    def fix_linux_paths(self):
        root = os.getcwd() + "/vendor/couchdb-1.0.1"
        for f in "bin/couchdb bin/couchjs bin/erl etc/couchdb/default.ini etc/init.d/couchdb etc/logrotate.d/couchdb lib/couchdb/erlang/lib/couch-1.0.1/ebin/couch.app".split():
    	    debug("fixing paths in", f)
    	    self.replace_file(os.path.join(root, f), "/home/anand/couchdb-1.0.1", root)
        
    def replace_file(self, path, pattern, replacement):
        text = open(path).read()
        text = text.replace(pattern, replacement)
        f = open(path, "w")
        f.write(text)
        f.close()
        
    def find_distro(self):
        uname = os.popen("uname").read().strip()
        if uname == "Darwin":
            return "osx"
        else:
            return "linux"
                        
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
        
    def ol_install(self, infobase):
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
        CouchDB().run_tasks(self.create_dbs, self.add_design_docs)
        
    def create_dbs(self, couchdb):
        info("    creating databases")
        couchdb.create_database("works")
        couchdb.create_database("editions")
        couchdb.create_database("seeds")
        
    def add_design_docs(self, couchdb):
        info("    adding design docs")
        couchdb.add_design_doc("works", "works/seeds")
        couchdb.add_design_doc("editions", "editions/seeds")
        couchdb.add_design_doc("seeds", "seeds/dirty")
        couchdb.add_design_doc("seeds", "seeds/sort")

class setup_accounts:
    """Task for creating openlibrary account and adding it to admin and api usergroups.
    """
    def run(self):
        info("setting up accounts...")
        Infobase().run_tasks(self.create_account, self.add_to_usergroups)
        
    def create_account(self, infobase):
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
        infobase.post("/account/update_user_details", {
            "username": "openlibrary",
            "verified": "true"
        })
        
    def add_to_usergroups(self, infobase):
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
                "key": "/usergroup/api",
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

def main():
    setup_dirs()
    global config
    config = read_config()
    
    tasks = [
        setup_virtualenv(),
        install_python_dependencies(),
    
        checkout_submodules(),
    
        install_couchdb(),
        install_solr(),
        install_couchdb_lucene(),
        
        setup_coverstore(),
        setup_ol(),
        setup_couchdb(),
        setup_accounts()
    ]
    
    for task in tasks:
        task.run()
    
if __name__ == '__main__':
    main()
