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
    install_couchdb()
    install_couchdb_lucene()
    
def mkdir_p(*paths):
    debug("mkdir -p ", *paths)
    for path in paths:
        if not os.path.exists(path):
            os.makedirs(path)
    
def install_solr():
    info("installing solr...")
    
    download_and_extract("http://www.apache.org/dist/lucene/solr/1.4.0/apache-solr-1.4.0.tgz")
    
    types = 'authors', 'editions', 'works', 'subjects', 'inside'
    paths = ["vendor/solr/solr/" + t for t in types]
    system("mkdir -p " + " ".join(paths))
    system("cp -R vendor/apache-solr-1.4.0/example/{etc,lib,logs,webapps,start.jar} vendor/solr/")
    system("cp conf/solr-biblio/solr.xml vendor/solr/solr/")

    solrconfig = open("vendor/apache-solr-1.4.0/example/solr/conf/solrconfig.xml").read()
    
    for t in types:
        if not os.path.exists('solr/solr/' + t + '/conf'):
            system("cp -r vendor/apache-solr-1.4.0/example/solr/conf vendor/solr/solr/%s/conf" % t)
            
        system('cp conf/solr-biblio/%s.xml vendor/solr/solr/%s/conf/schema.xml' % (t, t))
        
        f = 'vendor/solr/solr/' + t + '/conf/solrconfig.xml'
        debug("creating", f)
        write(f, solrconfig.replace("./solr/data", "./solr/%s/data" % t))
    
def install_couchdb():
    info("installing couchdb...")
    info("  downloading...")
    download_and_extract("http://www.archive.org/download/ol_vendor/apache-couchdb-1.0.1.tar.gz")
    
    info("  building...")
    system("bash -c 'cd vendor/apache-couchdb-1.0.1 && ./configure && make && make dev'")
    
    info("  copying config file...")
    system("cp conf/couchdb/local.ini vendor/apache-couchdb-1.0.1/etc/couchdb/local_dev.ini")
    
def install_couchdb_lucene():
    info("installing couchdb lucene...")
    download_and_extract("http://www.archive.org/download/ol_vendor/couchdb-lucene-0.6-SNAPSHOT-dist.tar.gz")    

def wget(url):
    filename = "vendor/" + url.split("/")[-1]
    if not os.path.exists(filename):
        system("wget %s -O %s" % (url, filename))
    return filename
    
def download_and_extract(url):
    filename = "vendor/" + url.split("/")[-1]
    if not os.path.exists(filename):
        system("wget %s -O %s" % (url, filename))
        
    dir = filename.replace(".tgz", "").replace(".tar.gz", "")
    if not os.path.exists(dir):
        system("cd vendor && tar xzf " + os.path.basename(filename))
        
def checkout_submodules():
    info("checking out git submodules ...")
    system("git submodule init")
    system("git submodule update")

def main():
    setup_dirs()
    
    global config
    config = read_config()
    setup_virtualenv()
    install_python_dependencies()
    install_vendor_packages()
    checkout_submodules()
    
if __name__ == '__main__':
    main()
