import sys
import unicodedata
import re
import os
from types import *

import web
import infogami.tdb as tdb
from infogami.tdb.tdb import Thing, NotFound, Things, LazyThing
from items import *
from lang import *

def setup ():
	def getvar (name, required=True):
		val = os.getenv (name)
		if required and val is None:
			raise Exception ("found no environment variable %s" % name)
		return val
	dbname = getvar ("PHAROS_DBNAME")
	dbuser = getvar ("PHAROS_DBUSER")
	dbpass = getvar ("PHAROS_DBPASS")
	web.config.db_parameters = dict(dbn='postgres', db=dbname, user=dbuser, pw=dbpass)
	web.db._hasPooling = False
	web.config.db_printing = False
	web.load()
	tdb.setup()

	global source_dir, thing_name
	source_dir = getvar ("PHAROS_SOURCE_DIR")

	global edition_prefix, author_prefix
	edition_prefix = getvar ("PHAROS_EDITION_PREFIX", False) or ""
	author_prefix = getvar ("PHAROS_AUTHOR_PREFIX", False) or ""

from marc.MARC21 import MARC21File, MARC21PrettyPrint

def probe (name):
	t = tdb.withName (name, site_object ())
	dump (t)

def probe_isbn (val):
	tt = Things (parent=site_object(), ISBN_10=val)
	for t in tt:
		dump (t)
	
def dump (t):
	print "----> %s" % t.name
	print repr (t.d)

	global source_dir
	source_name = t["source_name"]
	source_pos = t["source_record_pos"]
	if t.get ("marc_control_number"):
		source_type = "marc"
	elif t.get ("oca_identifier"):
		source_type = "oca"
	else:
		source_type = "onix"
	source_path = "%s/%s/%s" % (source_dir, source_type, source_name)

	if source_type == "marc":
		warn ("reading %s at %d ..." % (source_path, source_pos))
		f = open (source_path, "r")
		f.seek (source_pos)
		mf = MARC21File (f)
		r = mf.next ()
		MARC21PrettyPrint (r)

if __name__ == "__main__":
	setup ()
	# warn ("--> setup finished")
	if len (sys.argv) == 3:
		key = sys.argv[1]
		val = sys.argv[2]
		if key == "ISBN_10":
			warn ("probing things with %s='%s' ..." % (key, val))
			probe_isbn (val)
		else:
			die ("can't probe key '%s'" % key)
	elif len (sys.argv) == 2:
		thing_name = sys.argv[1]
		warn ("probing thing with name '%s' ..." % thing_name)
		probe (thing_name)
	else:
		die ("bad args")
