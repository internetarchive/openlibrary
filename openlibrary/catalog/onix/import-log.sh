#!/bin/sh

exec env PHAROS_DBNAME=dbglog PHAROS_DBUSER=pharos PHAROS_DBPASS=pharos PHAROS_SITE=site0 PHAROS_LOGFILE=/1/dbg/import-logs/dbglog URL_CACHE_DIR=urlcache python2.4 onix-import.py
