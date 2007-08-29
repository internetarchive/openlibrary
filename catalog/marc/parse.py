from types import *
from unicodedata import normalize

from MARC21 import *
from MARC21Biblio import *
from catalog.lang import *

from string import strip, join

def parser (file):
    f = MARC21BiblioFile (file)
    try:
        while True:
            try:
                item = f.next()
                yield massage_dict (item)
            except MARC21Exn, e:
                warn ("couldn't interpret item: %s" % e)
    except StopIteration:
        pass

def massage_value (v):
	if (isinstance (v, UnicodeType)):
		nv = normalize ('NFKC', v)
		return nv.encode ('utf8')
	elif (isinstance (v, ListType)):
		return map (massage_value, v)
	else:
		return v

def massage_dict (d):
	dd = {}
	for (k, v) in d.iteritems ():
		dd[k] = massage_value (v)
	return dd

def next (self):
	r = self.next_record ()
	item = {}
	for f in self.output_fields:
		v = r[f]
		if (isinstance (v, StringTypes) and v) or v is not None:
			item[f] = v
	return item

# authors

re_dates = re.compile (r'(\d{4})-(\d{4})?')

def author (self):
	a = None
	pn = self.get_field ("100")
	if pn:
		name = pn.get_elt ("a", None)
		if name:
			name = clean_name (name)
			a = { 'name': name }
			dates = pn.get_elt ("d", None)
			if dates:
				m = re_dates.search (dates)
				if m:
					a["birth_date"] = m.group (1)
					if m.group (2):
						a["death_date"] = m.group (2)
	else:
		ts = self.title_statement ()
		name = clean (join (ts.get_elts ("c"), ", "))
		if name:
			a = { 'name': name }
	return a

def authors (self):
	a = self.author ()
	if a: return [a]
	else: return None

# filters

re_isbn_chars = re.compile (r'^([\dX]+)')

def clean (s):
	return strip (s, " /.,;:")

def clean_name (s):
	return strip (s, " /,;:")

def normalize_isbn (s):
	m = re_isbn_chars.match (s)
	if m:
		isbn_chars = m.group (1)
		if (len (isbn_chars) == 13)
			return isbn_chars
		else:
			if (len (isbn_chars) == 10)
				return isbn_10_to_isbn_13 (isbn_10)
			else:
				warn ("bad ISBN: '%s'" % isbn_chars)
	return None

#		if lang == "|||":
#			if len(self.get_fields ("041")) > 0:
#				self.marc21_record.err ("has LANGUAGE CODE field")

#	def dewey_decimal_class (self):
#		classes = []
#		for ddcn in self.get_fields ("082"):
#			edition_number = ddcn.get_elt ("2", "?")
#			classification_numbers = ddcn.get_elts ("a")
#			classes.extend ([ "%s:%s"%(edition_number,cn) for cn in classification_numbers ])
#		return classes
