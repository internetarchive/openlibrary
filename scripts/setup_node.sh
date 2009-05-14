#! /bin/bash
# script to install all required software on OL nodes

# create OL folders
print "creating folders..."

OL_FOLDERS="/0/pharos /1/pharos /2/pharos /3/pharos"
mkdir -p $OL_FOLDERS
chgrp  pharos $OL_FOLDERS
chmod g+w $OL_FOLDERS

print "installing apt-get packages..."
aptitude install         \
    python-setuptools   \
    python-dev          \
    python2.5-psycopg2  \
    python-imaging      \
    git-core            \
    sqlite3

print "installing python packages..."
easy_install -Z \
    web.py      \
    flup        \
    simplejson  \
    pymarc
# setup code
print "getting openlibrary code..."
mkdir -p /0/pharos/code /0/pharos/scripts /0/pharos/services /0/pharos/etc
cd /0/pharos/code
git clone git://github.com/openlibrary/openlibrary.git

