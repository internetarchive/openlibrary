import sys
from cStringIO import StringIO
from elementtree import ElementTree
from types import *
from lang import *

def input_items (input):
	def buf2elt (buf):
		buf.seek (0, 0)
		e = None
		try:
			et = ElementTree.parse (buf)
			e = et.getroot ()
		except Exception, e:
			warn ("ignoring XML error: %s" % e)
		buf.close ()
		return e

	buf = None
	pos = None
	try:
		for line in input:
			if line.startswith('<?xml '):
				if buf: yield (buf2elt (buf), pos)
				pos = input.tell ()
				buf = StringIO ()
			else:
				buf.write (line)
		if buf: yield (buf2elt (buf), pos)
	except:
		warn ("breaking at input position %d on data:\n%s" % (pos, buf.getvalue ()))
		raise

def setval (x, k, v):
	x[k] = encode_val (v)

def addval (x, k, v):
	x.setdefault (k, []).append (encode_val (v))

def encode_val (v):
	if isinstance (v, StringType):
		return v
	elif isinstance (v, UnicodeType):
		return v.encode ('utf8')
	else:
		die ("couldn't encode value: %s" % repr (v))

element_dispatch = {
	'title': (setval, 'title'),
	'creator': (addval, 'author')
	}

def parse_item (r):
	# ElementTree.dump (e)
	e = {}
	for field in r:
		if field.text is None: continue
		action = element_dispatch.get (field.tag)
		if action:
			(f, k) = action
			v = field.text
			f (e, k, v)
	return e

def parse_input (input):
	n = 0
	for (r,pos) in input_items (input):
		if r is None: continue
		# parse_item (r)
		n += 1
		if n % 100 == 0:
			warn ("...... read %d records" % n)
	warn ("done.  read %d records" % n)

parse_input (sys.stdin)
