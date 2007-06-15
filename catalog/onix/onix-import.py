import web
import infogami.tdb as tdb
from infogami.tdb import NotFound, Things, LazyThing
from items import *
from onix import parser
import sys
import unicodedata
import re
import os
from lang import *
from types import *

source_name = None
source_path = None
edition_prefix = None
author_prefix = None

edition_records = set ([])
item_names = {}
#edition_names = set ([])
#author_names = {}

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
	logfile = getvar ("PHAROS_LOGFILE", False)
	if logfile:
		tdb.logger.set_logfile (open (logfile, "a"))
		sys.stderr.write ("logging to %s\n" % logfile)

	global source_name, source_path
	source_dir = getvar ("PHAROS_SOURCE_DIR")
	source_name = sys.argv[1]
	source_path = "%s/%s" % (source_dir, source_name)

	global edition_prefix, author_prefix
	edition_prefix = getvar ("PHAROS_EDITION_PREFIX", False) or ""
	author_prefix = getvar ("PHAROS_AUTHOR_PREFIX", False) or ""

	setup_names ()

def setup_names ():
	global item_names, edition_records, source_name

	warn ("walking the length and breadth of the database ...")
	author_type = Author.type ()
	edition_type = Edition.type ()
	walked = 0
	parent_id = site_object().id
	for r in web.query ("SELECT id,name FROM thing WHERE parent_id = $parent_id", vars=locals()):
		item_names[r.name] = r.id
	
	for r in web.query ("SELECT d1.value FROM datum AS d1, datum AS d2 WHERE d1.version_id=d2.version_id AND d1.key='source_record_lineno' AND d2.key='source_name' AND d2.value=$source_name", { 'source_name': source_name }):
		edition_records.add (int (r.value))

	warn ("noted %d items" % len (item_names))
	if len (edition_records) > 0:
		warn ("already have %d records from this source; they will be ignored" % len (edition_records))

def import_file (input):
	n = 0
	for x in parser (input):
		n += 1
		import_item (x)
		if n % 100 == 0:
			sys.stderr.write ("." * 30 + " read %d records\n" % n)
	sys.stderr.write ("\nread %d records\n" % n)

skipped = 0
imported = 0

def import_author (x):
	name = author_prefix + name_string (x["name"])
	a = None

	global item_names
	aid = item_names.get (name, None)
	if aid:
		a = LazyThing (aid)
		# warn ("---------------------------> already author %s" % name)
	else:
		a = Author (name, d=massage_dict (x))
		a.save ()
		item_names[name] = a.id
		# warn ("AUTHOR %s" % name)
	return a

def import_item (x):
	global skipped, imported

	global edition_records
	lineno = x["source_record_lineno"]
	if lineno in edition_records:
		skipped += 1
		if skipped % 100 == 0:
			warn ("skipped %d" % skipped)
		return

	# import the authors
	authors = map (import_author, x.get ("authors") or [])
	if x.get ("authors"):
		del x["authors"]

	# find a unique name for the edition
	global item_names
	name = None
	for n in edition_name_choices (x):
		nn = edition_prefix + n
		if nn not in item_names:
			name = nn
			break

	if not name:
		raise Exception ("couldn't find a unique name for %s" % x)

	e = Edition (name, d=massage_dict (x))
	global source_name
	e.source_name = source_name
	e.authors = authors
	e.save ()
	item_names[name] = e.id
	edition_records.add (e.source_record_lineno)
	imported += 1
	if imported % 100 == 0:
		warn ("imported %d" % imported)

	# sys.stderr.write ("EDITION %s\n" % name)

ignore_title_words = ['a', 'the']
tsep = '_'

def edition_name_choices (x):
	# use up to 25 chars of title, including last word
	title = name_safe (x['title'])
	title_words = [ w for w in title.split() if w.lower() not in ignore_title_words ]
	if len (title_words) == 0:
		raise Exception ("no usable title chars")
	ttail = title_words.pop (-1)
	tlen = len (ttail)
	name = ""
	nlen = 1 + tlen
	if title_words:
		name = title_words.pop (0)
		nlen = len (name) + 1 + tlen
		while title_words:
			w = title_words.pop (0)
			wlen = len (w)
			if nlen + 1 + wlen < 25:
				name += "_" + w
				nlen += 1 + wlen
	if name:
		name += "_"
	name += ttail
	name = name[0:30]
	yield name

	ed_number = x.get ('edition_number')
	if ed_number:
		name = tsep.join ([name, name_string (ed_number)])
		yield name

	ed_type = x.get ('edition_type')
	if ed_type:
		name = tsep.join ([name, name_string (ed_type)])
		yield name

	ed = x.get ('edition')
	if ed:
		name = tsep.join ([name, name_string (ed)])
		yield name

	format = x.get ('physical_format')
	if format:
		name = tsep.join ([name, name_string (format)])
		yield name

	nlen = len (name)
	n = 0
	while True:
		name = name[:nlen] + tsep + "%d" % n
		yield name
		n += 1

	return

re_name_safe = re.compile (r'[^a-zA-Z0-9]')
def name_safe (s):
	s = asciify (s)
	s = s.replace ("'", "")
	return re.sub (re_name_safe, ' ', s)

def name_string (s):
	s = name_safe (s)
	words = s.split ()
	return '_'.join (words)

def asciify (s):
	return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore')

def massage_value (v):
	if (isinstance (v, UnicodeType)):
		return v.encode ('utf8')
	elif (isinstance (v, ListType)):
		return map (massage_value, v)
	else:
		return v

def massage_dict (d):
	dd = {}
	for (k, v) in d.iteritems ():
		dd[k] = massage_value (v)
	return dd

if __name__ == "__main__":
	setup()
	sys.stderr.write ("--> setup finished\n")
	import_file (open (source_path, "r"))
	sys.stderr.write ("--> import finished\n")
