import os
from types import *
import urlparse
from urlcache import URLCache
import xml.sax
from xml.sax.handler import *
import sys

class CachingEntityResolver (EntityResolver):
	def __init__ (self, parser, dir):
		self.parser = parser
		if not os.path.isdir (dir):
			raise Exception ("CachingEntityResolver: no such directory: %s" % dir)
		self.cache = URLCache (dir)

	def resolveEntity (self, pubid, sysid):
		parser_sysid = self.parser.getSystemId ()
		src = None
		if sysid.startswith ("http:"):
			src = self.resolveURL (sysid)
		elif isinstance (parser_sysid, StringTypes) and parser_sysid.startswith ("http:"):
			src = self.resolveURL (sysid, parser_sysid)
		if not src:
			src = EntityResolver.resolveEntity (self, p, s)
		return src

	def resolveURL (self, sysid, base = ""):
		url = urlparse.urljoin (base, sysid)
		source = xml.sax.xmlreader.InputSource (url)
		f = self.cache.get (url)
		source.setByteStream (f)
		return source

def collector_parse (input, dispatch):
	parser = xml.sax.make_parser ()
	parser.setFeature (xml.sax.handler.feature_namespaces, 1)
	handler = CollectorHandler (parser, dispatch)
	# parser.setContentHandler (handler)	# CollectorHandler sets ContentHandler
	parser.parse (input)
	return handler.get_value ()

class CollectorHandler:
	def __init__ (self, parser, base):
		self.parser = parser
		base_collector = None
		if isinstance (base, Collector):
			base_collector = base
		else:
			base_collector = NodeCollector (base)
		self.collectors = [base_collector]
		base_collector.start (None, self)
		self.set_handler ()

	def get_value (self):
		if len (self.collectors) == 1:
			return self.collectors[0].finish ()
		else:
			raise Exception ("CollectorHandler.get_value(): collection not finished")

	def top_collector (self):
		if not len (self.collectors):
			return None
		else:
			return self.collectors[-1]

	def push_collector (self, collector):
		self.collectors.append (collector)
		self.set_handler ()

	def pop_collector (self):
		self.collectors.pop ()
		self.set_handler ()

	def set_handler (self):
		self.parser.setContentHandler (self.top_collector ())

class Collector (ContentHandler):
	def start (self, parent, handler):
		self.parent = parent
		self.handler = handler
	def end (self):
		self.handler.pop_collector ()
		self.handler = None
		value = self.finish ()
		if not isinstance (value, CollectorNoneValue):
			self.parent.collect (value)
		self.parent = None
	def finish (self):
		pass
	def endElementNS (self, name, qname):
		self.end ()

class TextCollector (Collector):
	def __init__ (self):
		self.value = None
	def characters (self, content):
		self.value = content
	def finish (self):
		return self.value

class NodeCollector (Collector):
	def __init__ (self, collector_table, strict=False):
		self.collector_table = collector_table
		self.strict = strict
		self.ignoring = 0
		self.value = collector_none
	def startElementNS (self, name, qname, attrs):
		if self.ignoring:
			self.ignoring += 1
		else:
			(uri, localname) = name
			c_maker = self.collector_table.get (localname) or self.collector_table.get (collector_any)
			if c_maker:
				c = c_maker (name, attrs)
				c.start (self, self.handler)
				self.handler.push_collector (c)
			else:
				if self.strict:
					raise Exception ("no handler for element '%s'; handlers: %s" % (localname, self.collector_table.keys ()))
				else:
					self.ignoring += 1
	def endElementNS (self, name, qname):
		if self.ignoring:
			self.ignoring -= 1
		else:
			self.end ()
	def collect (self, value):
		self.value = value
	def finish (self):
		return self.value

class NamedCollector (NodeCollector):
	def __init__ (self, name, collector_table):
		NodeCollector.__init__ (self, collector_table)
		self.name = name
	def finish (self):
		if self.value is collector_none:
			return collector_none
		else:
			return (self.name, self.value)

class ListCollector (NodeCollector):
	def __init__ (self, collector_table):
		NodeCollector.__init__ (self, collector_table)
		self.values = []
	def collect (self, value):
		self.values.append (value)
	def finish (self):
		return self.values

class DictCollector (NodeCollector):
	def __init__ (self, collector_table):
		NodeCollector.__init__ (self, collector_table)
		self.values = {}
	def collect (self, key_value):
		(key, value) = key_value
		if self.values.get (key):
			raise Exception ("dictionary key '%s' is already mapped" % key)
		else:
			self.values[key] = value
	def finish (self):
		return self.values

class CollectorValue (NodeCollector):
	def __init__ (self, val):
		NodeCollector.__init__ (self, {}, strict=False)
		self.collect (val)

class CollectorNoneValue: pass
collector_none = CollectorNoneValue ()
def CollectorNone ():
	return CollectorValue (collector_none)

class CollectorAnyElement: pass
collector_any = CollectorAnyElement ()
