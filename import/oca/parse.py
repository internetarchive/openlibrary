import sys
from cStringIO import StringIO
from xml.parsers.expat import error as xml_error
from elementtree import ElementTree
from types import *
from lang import *

def input_items (input):
	def buf2elt (buf):
		buf.seek (0, 0)
		elt = None
		try:
			et = ElementTree.parse (buf)
			elt = et.getroot ()
		except xml_error, e:
			elt = None
			warn ("ignoring XML error: %s" % e)
		buf.close ()
		return elt

	buf = None
	bufpos = None
	for (line, linepos) in lines_positions (input):
		if line.startswith('<?xml '):
			if buf is not None:
				yield (buf2elt (buf), bufpos)
			buf = StringIO ()
			bufpos = None
		else:
			if buf: # this lets us start anywhere and pick up the next record
				if bufpos is None:
					bufpos = linepos
				buf.write (line)
	if buf is not None:
		yield (buf2elt (buf), bufpos)

def setval (x, v, k):
	x[k] = v

def addval (x, v, k, translate=lambda x: x):
	v = translate (v)
	vv = x.get (k)
	if vv:
		vv.append (v)
	else:
		x[k] = [v]

def concval (x, v, k, sep=" "):
	vv = x.get (k)
	if vv:
		x[k] = vv + sep + v
	else:
		x[k] = v

def thingify_with (field):
	return lambda v: { field: v }

element_dispatch = {
	'title': (setval, 'title'),
	'creator': (addval, 'authors', thingify_with ('name')),
	'subject': (addval, 'subject'),
	'description': (concval, 'description', "; "),
	'publisher': (setval, 'publisher'),
	'date': (setval, 'publish_date'),
	# if can be a language_code, enter that and also provide language, else store as language
	'language': (setval, 'language'),
	'sponsor': (setval, 'scan_sponsor'),
	'contributor': (setval, 'scan_contributor'),
	'identifier': (setval, 'oca_identifier')
	}

ignored = {}

def parse_item (r):
	global ignored
	e = {}
	for field in r:
		text = field.text
		if text is None: continue
		tag = field.tag
		action = element_dispatch.get (tag)
		if action:
			f = action[0]
			args = action[1:]
			v = encode_val (text)
			f (e, v, *args)
		else:
			count = ignored.get (tag) or 0
			ignored[tag] = count + 1
	return e

limit = 1000
def test_input (input):
	n = 0
	global ignored
	ignored = {}
	for (r,pos) in input_items (input):
		# if limit and n == limit: break
		if r is None: continue
		o = parse_item (r)
		print o
		n += 1
		if n % 100 == 0:
			warn ("...... read %d records" % n)
	warn ("ignored:")
	for (tag,count) in ignored.iteritems ():
		warn ("\t%d\t%s" % (count, tag))
	warn ("done.  read %d records" % n)

def parser (input):
	for (r,pos) in input_items (input):
		if r is None: continue
		d = parse_item (r)
		d["source_record_pos"] = pos
		yield d

def encode_val (v):
	if isinstance (v, StringType):
		return v
	elif isinstance (v, UnicodeType):
		return v.encode ('utf8')
	else:
		die ("couldn't encode value: %s" % repr (v))

# parse_input (sys.stdin)
