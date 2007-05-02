# TODO
# - source record identifier
#   - two fields -- source-id and record-id ?
#   - pre-fetch the set of these that are already in the db?
# SCHEMA
# author
# - name
# - inverted_name

import web
import infogami.tdb as tdb
from infogami.tdb import NotFound, Things
from items import *
from onix import onix_parser
import sys
import unicodedata
import re
import os
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
	logfile = getvar ("PHAROS_LOGFILE", False)
	if logfile:
		tdb.logger.set_logfile (open (logfile, "a"))
		sys.stderr.write ("logging to %s\n" % logfile)

def clear ():
	web.query('delete from datum where version_id > 2')
	web.query('delete from version where thing_id > 2')
	web.query('delete from thing where id > 2')

def import_file (input):
	n = 0
	for x in onix_parser (input):
		n += 1
		import_item (x)
		if n % 100 == 0:
			sys.stderr.write ("." * 30 + " read %d records\n" % n)
	sys.stderr.write ("\nread %d records\n" % n)

def dump_items ():
	for i in Things (parent=site_object()):
		print "> ", i.title

used_names = {}
skipped = 0
imported = 0

def import_author (x):
	name = name_string (x["name"])
	a = None
	try:
		Item.withName (name)
		a = Author.withName (name)
		warn ("---------------------------> already author %s" % name)
	except:
		a = Author (name, d=x)
		a.save ()
		warn ("AUTHOR %s" % name)
	return a

def import_item (x):
	global used_names, skipped, imported

	# check whether this record has already been imported
	isbn = x["ISBN_13"]
	for e in Things (ISBN_13=isbn):
		skipped += 1
		if skipped % 100 == 0:
			warn ("skipped %d" % skipped)
		return

	# import the authors
	authors = map (import_author, x.get ("authors") or [])
	if x.get ("authors"):
		del x["authors"]

	# find a unique name for the edition
	name = None
	for n in edition_names (x):
		if not n in used_names and not Item.withName (n, default=None):
			name = n
			used_names[n] = True
			break
	if not name:
		raise Exception ("couldn't find a unique name for %s" % x)

	e = Edition (name, d=x)
	e.authors = authors
	e.save ()
	imported += 1
	if imported % 100 == 0:
		warn ("imported %d" % imported)

	sys.stderr.write ("EDITION %s\n" % name)

ignore_title_words = ['a', 'the']
tsep = '_'

def edition_names (x):
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
		name = tsep.join ([name, name_string (ed_type)])
		yield name

	format = x.get ('physical_format')
	if format:
		name = tsep.join ([name, name_string (format)])
		yield name

	# author_names is now authors (dicts)
	# authors = x.get ('author_names')
	# if authors:
	# 	name = tsep.join ([name, name_string (authors[0])])
	# 	yield name

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

if __name__ == "__main__":
	setup()
	sys.stderr.write ("--> setup finished\n")
	import_file (sys.stdin)
	sys.stderr.write ("--> import finished\n")
	# dump_items ()
