#!/bin/sh

exec env PHAROS_DBNAME=dbgtest PHAROS_DBUSER=dbg PHAROS_SITE=site0 URL_CACHE_DIR=urlcache python2.4 onix-import.py
