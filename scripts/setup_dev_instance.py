#! /usr/bin/env python
"""Script to install OL dev instance.
"""
import ConfigParser
import os
import shlex
import subprocess
import sys
import time

config = None
INTERP = None

CWD = os.getcwd()

class CouchDBInstaller:
    """CouchDB Installer for linux and osx.
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
        system("cp conf/couchdb/local.ini vendor/couchdb-1.0.1/etc/")
        
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
    
def setup_virtualenv():
    """Creates a new virtualenv and exec this script using python from that
    virtual env.
    """
    global INTERP
    
    pyenv = os.path.expanduser(config['virtualenv'])
    INTERP = pyenv + "/bin/python"
    
    if sys.executable != INTERP:
        info("creating virtualenv at", pyenv)
        system("virtualenv " + pyenv)
        
        info("restarting the script with python from", INTERP)
        os.execl(INTERP, INTERP, *sys.argv)
        
def install_python_dependencies():
    info("installing python dependencies")
    system(INTERP + " setup.py develop")
    
def install_vendor_packages():
    install_solr()
    install_couchdb_lucene()
    CouchDBInstaller().run()
    
    
def mkdir_p(*paths):
    debug("mkdir -p ", *paths)
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)
    
def install_solr():
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
    
def install_couchdb_lucene():
    info("installing couchdb lucene...")
    download_and_extract("http://www.archive.org/download/ol_vendor/couchdb-lucene-0.6-SNAPSHOT-dist.tar.gz")    

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
        
def checkout_submodules():
    info("checking out git submodules ...")
    system("git submodule init")
    system("git submodule update")
    
def initialize_databases():
    info("initializing databases...")
    initialize_postgres_database()
    
def initialize_postgres_database():
    info("  creating postgres db...")
    system("createdb openlibrary")
    system("python openlibrary/core/schema.py | psql openlibrary")
    
    stdout = open("var/log/install.log", 'a')
    info("  starting infobase server to initialize OL")
    cmd = INTERP + " ./scripts/infobase-server conf/infobase.yml 7500"
    p = subprocess.Popen(cmd.split(), stdout=stdout, stderr=stdout)
    time.sleep(2)
    try:
        info("  running OL setup script...")
        system(INTERP + " ./scripts/openlibrary-server conf/openlibrary.yml install")
    finally:
        info("  stopping infobase server...")
        p.kill()

def main():
    setup_dirs()
    
    global config
    config = read_config()
    setup_virtualenv()
    install_python_dependencies()
    install_vendor_packages()
    checkout_submodules()
    initialize_databases()
    
if __name__ == '__main__':
    main()
