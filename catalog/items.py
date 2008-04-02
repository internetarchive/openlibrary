### this has fallen out of sync with ThingDB and is no longer used

import os

from infogami import tdb
from infogami.tdb import Thing, NotFound
from lang import memoized
 
class Unspecified: pass
unspecified = Unspecified ()

class ItemTypeError (Exception): pass

class Item (Thing):

	def __init__ (self, name=None, d={}):
		id = None
		parent = site_object ()
		type = self.__class__.type ()
		Thing.__init__ (self, id, name, parent, type, d)
		self._dirty = True

	type_thing = None

	@classmethod
	def type (cl):
		if not cl.type_thing:
			try:
				cl.type_thing = tdb.withName (cl.typename (), tdb.metatype)
			except NotFound:
				cl.type_thing = tdb.new (cl.typename (), tdb.metatype, tdb.metatype)
				cl.type_thing.save ()
		return cl.type_thing

	@classmethod
	def typename (cl):
		return "item:" + str (cl).split ('.')[-1]

	@classmethod
	def withName (cl, name, default=unspecified):
		parent = site_object ()
		t = None
		try:
			t = tdb.withName (name, parent)
		except NotFound:
			if default is unspecified:
				raise
			else:
				return default
		# if t.type != cl.type ():
		#	raise ItemTypeError ("object with name '%s' is not of type %s" % (name, cl.typename ()))
		t.__class__ = cl
		return t

@memoized
def site_object ():
	site_name = os.getenv ("PHAROS_SITE")
	if not site_name:
		raise Exception ("no site name found in PHAROS_SITE environment variable")

	site_parent = None
	try:
		site_parent = tdb.withName ("site", tdb.metatype)
	except NotFound:
		site_parent = tdb.new ("site", tdb.metatype, tdb.metatype)
		site_parent.save ()

	site = None
	try:
		site = tdb.withName (site_name, site_parent)
	except NotFound:
		site = tdb.new (site_name, site_parent, tdb.metatype)
		site.save ()
	return site

class Work (Item):
	@classmethod
	def typename (cl): return "work"

class Edition (Item):
	@classmethod
	def typename (cl): return "edition"

class Author (Item):
	@classmethod
	def typename (cl): return "author"
