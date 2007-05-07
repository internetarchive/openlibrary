from MARC21 import *
from MARC21Biblio import *
from lang import *
from types import *

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
