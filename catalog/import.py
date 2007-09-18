import sys
import unicodedata
import re
import os
from types import *

import web
from infogami.tdb.tdb import NotFound, Things, Thing, LazyThing
import infogami.tdb.tdb
from lang import *

global tdb
tdb = None

from oca.parse import parser as oca_parser
from marc.parse import parser as marc_parser
from onix.parse import parser as onix_parser

edition_prefix = None
author_prefix = None

edition_records = set ([])
item_names = {}

def setup ():
	dbname = getvar ("PHAROS_DBNAME")
	dbuser = getvar ("PHAROS_DBUSER")
	dbpass = getvar ("PHAROS_DBPASS", False)
	web.config.db_parameters = dict(dbn='postgres', db=dbname, user=dbuser)
	if dbpass:
		web.config.db_parameters['pw'] = dbpass
	web.db._hasPooling = False
	web.config.db_printing = False
	web.load()

	global tdb
	tdb = infogami.tdb.tdb.SimpleTDBImpl ()
	tdb.setup ()

	logfile = getvar ("PHAROS_LOGFILE", False)
	if logfile:
		tdb.logger.set_logfile (open (logfile, "a"))
		sys.stderr.write ("logging to %s\n" % logfile)

	global edition_prefix, author_prefix
	edition_prefix = getvar ("PHAROS_EDITION_PREFIX", False) or ""
	author_prefix = getvar ("PHAROS_AUTHOR_PREFIX", False) or ""

	setup_names ()

def setup_names ():
	global item_names, edition_records

	# suck in all the Thing names in the database, in order to have them in
	# memory when trying to generate a unique name.  (note that this assumes
	# the database is not being changed by others during the import.)

	warn ("getting all Thing names from the database ...")
	for t in Things(tdb):
		item_names[t.name] = t.id
	
	# the above code is not tested, and used to be this:
	#	for r in web.query ("SELECT id,name FROM thing WHERE parent_id = $parent_id", vars=locals()):
	#		item_names[r.name] = r.id

	warn ("getting all Edition source_record_ids from the database ...")
	for e in Things(tdb, type=edition_type()):
		ids = e.get ('source_record_id', [])
		for id in ids:
			edition_records.add (id)

	# the above code is not tested, and used to be this:
	# (because records used to be identified by <source_name,source_record_pos>
	#	for r in web.query ("SELECT d1.value FROM datum AS d1, datum AS d2 WHERE d1.version_id=d2.version_id AND d1.key='source_record_pos' AND d2.key='source_name' AND substr(d2.value,0,250)=$source_name", { 'source_name': source_name }):
	#		edition_records.add (int (r.value))

	warn ("noted %d items" % len (item_names))
	if len (edition_records) > 0:
		warn ("already have %d records from this source; they will be ignored" % len (edition_records))

parsers = {
	'onix': onix_parser,
	'marc': marc_parser,
	'oca': oca_parser
	}

def import_source (source_locator):
	# source_locator: an Archive item id; e.g., "marc_records_scriblio_net"
	source_type = get_source_type (source_locator)
	source_id = get_source_id (source_locator)
	file_locators = get_file_locators (source_locators)

	for file_locator in file_locators:
		input = open_file_locator (file_locator)
		import_file (source_type, source_id, file_locator, input)
	
def import_file (source_type, source_id, file_locator, input):
	# file_locator: an Archive item id plus path to file; e.g., "marc_records_scriblio_net/part01.dat"

	parser = parsers.get (source_type)
	if not parser:
		die ("sorry, we don't have a parser for catalogs of type '%s'" % source_type)

	n = 0
	# web.transact ()
	for x in parser (source_id, file_locator, input):
		n += 1
		import_item (x)
		# if n % 1000 == 0:
		# 	web.commit ()
		# 	web.transact ()
		if n % 1000 == 0:
			sys.stderr.write ("." * 30 + " read %d records\n" % n)
	# web.commit ()
	sys.stderr.write ("\nread %d records\n" % n)

def get_source_file_locators (source_locator):
	# this should use HTTP to query the Archive item at source_locator
	# and look at OpenLibrary-specific metadata there (not yet invented) to determine the
	# list of file_locators
	return []

def get_source_type (source_locator):
	# this should use HTTP to query the Archive item at source_locator
	# and look at OpenLibrary-specific metadata there (not yet invented) to determine the type
	return "marc"

def get_source_id (source_locator):
	# this should use HTTP to query the Archive item at source_locator
	# and look at OpenLibrary-specific metadata there (not yet invented) to determine the source id
	return "LC"

def open_file_locator (file_locator):
	# this should use HTTP to retrieve the data from the indicated file,
	# or something equivalent like consulting a local cache.
	die ("unimplemented")

skipped = 0
imported = 0

def import_author (x):
	name = name_string (x["name"])
	name = name[0:30].rstrip ('_')
	if len (name) == 0:
		warn ("couldn't make name for author:\n%s" % x)
		return None
	name = author_prefix + name

	global item_names
	aid = item_names.get (name, None)
	a = None
	if aid:
		a = LazyThing (aid)
		warn ("(AUTHOR %s)" % name)
	else:
		a = make_author (name, x)
		a.save ()
		item_names[name] = a.id
		warn ("AUTHOR %s" % name)
	return a

def import_item (x):
	global skipped, imported

	record_locator = x['source_record_loc']
	warn ("import_item: %s" % record_locator)

	global edition_records
	for record_id in x["source_record_id"]:
		if record_id in edition_records:
			# XXX: just skip the record ... but what we should
			# actually do is compare its transaction date (ask kcoyle how to
			# determine this for the various formats) to that of the record
			# we already have, and replace it if the new one is more recent.
			skipped += 1
			if skipped % 100 == 0:
				warn ("skipped %d" % skipped)
			return

	if not x.get ("title"):
		# warn ("no title in record %s" % record_locator)
		return

	# import the authors; XXX: don't save until edition goes through?
	authors = filter (lambda x: x is not None, map (import_author, x.get ("authors") or []))
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
		warn ("couldn't find a unique name for %s" % x)
		return

	e = make_edition (name, x)
	e.authors = authors
	e.save ()
	item_names[name] = e.id
	edition_records.update (e.get ('source_record_id', []))
	imported += 1
	if imported % 100 == 0:
		warn ("imported %d" % imported)

	warn ("EDITION %s" % name)

def make_edition (name, data):
	type = edition_type ()
	return make_thing (name, type, data)

def make_author (name, data):
	type = author_type ()
	return make_thing (name, type, data)

def make_thing (name, type, data):
	id = None
	parent = site_object ()
	latest_revision = None
	v = None
	return Thing (tdb, id, name, parent, latest_revision, v, type, data)
	
@memoized
def edition_type (): return type_object ("edition")

@memoized
def author_type (): return type_object ("author")

def type_object (type_name):
	try:
		return tdb.withName ("type/" + type_name, site_object ())
	except NotFound:
		die ("can't find type object for type '%s'" % type_name)
	
@memoized
def site_object ():
	site_name = os.getenv ("PHAROS_SITE")
	if not site_name:
		raise Exception ("no site name found in PHAROS_SITE environment variable")
	try:
		return tdb.withName (site_name, tdb.root)
	except NotFound:
		raise Exception ("no site object for site named '%'" % site_name)

ignore_title_words = ['a', 'the']
tsep = '_'

def edition_name_choices (x):
	# use up to 25 chars of title, including first and last words
	title = name_safe (x['title'])
	title_words = [ w for w in title.split() if w.lower() not in ignore_title_words ]
	if len (title_words) == 0:
		warn ("no usable title chars")
		return
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
	name = name[0:40].rstrip (tsep)
	yield name

	def extensions (name):
		ed = x.get ('edition')
		if ed:
			name = tsep.join ([name, name_string (ed)])
			yield name

		for format in x.get ('physical_format', []):
			name = tsep.join ([name, name_string (format)])
			yield name

	if len (name) < 40:
		for n in extensions (name):
			if len (n) > 40:
				name = n[0:40].rstrip (tsep)
				yield name
				break
			else:
				name = n
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
	if isinstance (s, StringType):
		return s
	elif isinstance (s, UnicodeType):
		return unicodedata.normalize('NFKC', s).encode('ASCII', 'ignore')
	else:
		die ("not a string: %s" % s)

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

def getvar (name, required=True):
	val = os.getenv (name)
	if required and val is None:
		raise Exception ("found no environment variable %s" % name)
	return val

def import_cached_file ():
	# this is the "old" approach to importing; ideally, we would
	# instead use import_source(), which gets all its parameters from
	# metadata stored at the Archive item

	source_type = sys.argv[1]
	source_id = sys.argv[2]
	file_locator = sys.argv[3]
	input = sys.stdin

	source_pos = 0
	if len (sys.argv) > 4:
		source_pos = int (sys.argv[3])
	if source_pos:
		input.seek (source_pos)

	import_file (source_type, source_id, file_locator, input)

if __name__ == "__main__":
	setup()
	sys.stderr.write ("--> setup finished\n")
	import_cached_file ()
	sys.stderr.write ("--> import finished\n")

