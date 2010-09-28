#!/bin/sh

export PHAROS_DBNAME=dbgtest
export PHAROS_DBUSER=dbg
export PHAROS_SITE=site1

export PHAROS_EDITION_PREFIX="b/"
export PHAROS_AUTHOR_PREFIX="a/"

export URL_CACHE_DIR=urlcache 
export PYTHONPATH=/home/dbg/lib/python

exec python2.4 onix-import.py
