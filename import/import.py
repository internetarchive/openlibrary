import web
import infogami.tdb as tdb
from infogami.tdb import NotFound, Things, LazyThing
from items import *
import sys
import unicodedata
import re
import os
from lang import *
from types import *

import oca
import marc

source_name = None
source_type = None
source_path = None
source_pos = None
edition_prefix = None
author_prefix = None

edition_records = set ([])
item_names = {}

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

	global source_name, source_type, source_path, source_pos
	source_dir = getvar ("PHAROS_SOURCE_DIR")
	source_type = sys.argv[1]
	source_name = sys.argv[2]
	source_pos = 0
	if len (sys.argv) > 3:
		source_pos = int (sys.argv[3])
	source_path = "%s/%s/%s" % (source_dir, source_type, source_name)
	warn ("reading %s at %d ..." % (source_path, source_pos))

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
	
	for r in web.query ("SELECT d1.value FROM datum AS d1, datum AS d2 WHERE d1.version_id=d2.version_id AND d1.key='source_record_pos' AND d2.key='source_name' AND substr(d2.value,0,250)=$source_name", { 'source_name': source_name }):
		edition_records.add (int (r.value))

	warn ("noted %d items" % len (item_names))
	if len (edition_records) > 0:
		warn ("already have %d records from this source; they will be ignored" % len (edition_records))

parsers = {
	'oca': oca.parser,
	'marc': marc.parser
	}

def import_file (type, input):
	parser = parsers[type]
	n = 0
	web.transact ()
	for x in parser (input):
		n += 1
		import_item (x)
		if n % 1000 == 0:
			web.commit ()
			web.transact ()
		if n % 1000 == 0:
			sys.stderr.write ("." * 30 + " read %d records\n" % n)
	web.commit ()
	sys.stderr.write ("\nread %d records\n" % n)

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
		a = Author (name, d=massage_dict (x))
		a.save ()
		item_names[name] = a.id
		warn ("AUTHOR %s" % name)
	return a

def import_item (x):
	global skipped, imported

	global edition_records
	pos = x["source_record_pos"]
	if pos in edition_records:
		skipped += 1
		if skipped % 100 == 0:
			warn ("skipped %d" % skipped)
		return

	if not x.get ("title"):
		# warn ("no title in record at position %d" % pos)
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

	e = Edition (name, d=massage_dict (x))
	global source_name
	e.source_name = source_name
	e.authors = authors
	e.save ()
	item_names[name] = e.id
	edition_records.add (e.source_record_pos)
	imported += 1
	if imported % 100 == 0:
		warn ("imported %d" % imported)

	warn ("EDITION %s" % name)

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
		return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore')
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

if __name__ == "__main__":
	setup()
	sys.stderr.write ("--> setup finished\n")

	f = open (source_path, "r")
	if source_pos:
		f.seek (source_pos)
	import_file (source_type, f)
	sys.stderr.write ("--> import finished\n")
