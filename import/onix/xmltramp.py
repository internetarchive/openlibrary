"""xmltramp: Make XML documents easily accessible."""

__version__ = "2.17"
__author__ = "Aaron Swartz"
__credits__ = "Many thanks to pjz, bitsko, and DanC."
__copyright__ = "(C) 2003-2006 Aaron Swartz. GNU GPL 2."

if not hasattr(__builtins__, 'True'): True, False = 1, 0
def isstr(f): return isinstance(f, type('')) or isinstance(f, type(u''))
def islst(f): return isinstance(f, type(())) or isinstance(f, type([]))

empty = {'http://www.w3.org/1999/xhtml': ['img', 'br', 'hr', 'meta', 'link', 'base', 'param', 'input', 'col', 'area']}

def quote(x, elt=True):
	if elt and '<' in x and len(x) > 24 and x.find(']]>') == -1: return "<![CDATA["+x+"]]>"
	else: x = x.replace('&', '&amp;').replace('<', '&lt;').replace(']]>', ']]&gt;')
	if not elt: x = x.replace('"', '&quot;')
	return x

class Element:
	def __init__(self, name, attrs=None, children=None, prefixes=None, line=None):
		if islst(name) and name[0] == None: name = name[1]
		if attrs:
			na = {}
			for k in attrs.keys():
				if islst(k) and k[0] == None: na[k[1]] = attrs[k]
				else: na[k] = attrs[k]
			attrs = na
		
		self._name = name
		self._attrs = attrs or {}
		self._dir = children or []
		
		prefixes = prefixes or {}
		self._prefixes = dict(zip(prefixes.values(), prefixes.keys()))
		
		if prefixes: self._dNS = prefixes.get(None, None)
		else: self._dNS = None

		self._line = line
	
	def __repr__(self, recursive=0, multiline=0, inprefixes=None):
		def qname(name, inprefixes): 
			if islst(name):
				if inprefixes[name[0]] is not None:
					return inprefixes[name[0]]+':'+name[1]
				else:
					return name[1]
			else:
				return name
		
		def arep(a, inprefixes, addns=1):
			out = ''

			for p in self._prefixes.keys():
				if not p in inprefixes.keys():
					if addns: out += ' xmlns'
					if addns and self._prefixes[p]: out += ':'+self._prefixes[p]
					if addns: out += '="'+quote(p, False)+'"'
					inprefixes[p] = self._prefixes[p]
			
			for k in a.keys():
				out += ' ' + qname(k, inprefixes)+ '="' + quote(a[k], False) + '"'
			
			return out
		
		inprefixes = inprefixes or {u'http://www.w3.org/XML/1998/namespace':'xml'}
		
		# need to call first to set inprefixes:
		attributes = arep(self._attrs, inprefixes, recursive) 
		out = '<' + qname(self._name, inprefixes)  + attributes 
		
		if not self._dir and (self._name[0] in empty.keys() 
		  and self._name[1] in empty[self._name[0]]):
			out += ' />'
			return out
		
		out += '>'

		if recursive:
			content = 0
			for x in self._dir: 
				if isinstance(x, Element): content = 1
				
			pad = '\n' + ('\t' * recursive)
			for x in self._dir:
				if multiline and content: out +=  pad 
				if isstr(x): out += quote(x)
				elif isinstance(x, Element):
					out += x.__repr__(recursive+1, multiline, inprefixes.copy())
				else:
					raise TypeError, "I wasn't expecting "+`x`+"."
			if multiline and content: out += '\n' + ('\t' * (recursive-1))
		else:
			if self._dir: out += '...'
		
		out += '</'+qname(self._name, inprefixes)+'>'
			
		return out
	
	def __unicode__(self):
		text = ''
		for x in self._dir:
			text += unicode(x)
		return ' '.join(text.split())
		
	def __str__(self):
		return self.__unicode__().encode('utf-8')
	
	def __getattr__(self, n):
		if n[0] == '_': raise AttributeError, "Use foo['"+n+"'] to access the child element."
		if self._dNS: n = (self._dNS, n)
		for x in self._dir:
			if isinstance(x, Element) and x._name == n: return x
		raise AttributeError, 'No child element named %s' % repr(n)
		
	def __hasattr__(self, n):
		for x in self._dir:
			if isinstance(x, Element) and x._name == n: return True
		return False
		
 	def __setattr__(self, n, v):
		if n[0] == '_': self.__dict__[n] = v
		else: self[n] = v
 

	def __getitem__(self, n):
		if isinstance(n, type(0)): # d[1] == d._dir[1]
			return self._dir[n]
		elif isinstance(n, slice(0).__class__):
			# numerical slices
			if isinstance(n.start, type(0)): return self._dir[n.start:n.stop]
			
			# d['foo':] == all <foo>s
			n = n.start
			if self._dNS and not islst(n): n = (self._dNS, n)
			out = []
			for x in self._dir:
				if isinstance(x, Element) and x._name == n: out.append(x) 
			return out
		else: # d['foo'] == first <foo>
			if self._dNS and not islst(n): n = (self._dNS, n)
			for x in self._dir:
				if isinstance(x, Element) and x._name == n: return x
			raise KeyError
	
	def __setitem__(self, n, v):
		if isinstance(n, type(0)): # d[1]
			self._dir[n] = v
		elif isinstance(n, slice(0).__class__):
			# d['foo':] adds a new foo
			n = n.start
			if self._dNS and not islst(n): n = (self._dNS, n)

			nv = Element(n)
			self._dir.append(nv)
			
		else: # d["foo"] replaces first <foo> and dels rest
			if self._dNS and not islst(n): n = (self._dNS, n)

			nv = Element(n); nv._dir.append(v)
			replaced = False

			todel = []
			for i in range(len(self)):
				if self[i]._name == n:
					if replaced:
						todel.append(i)
					else:
						self[i] = nv
						replaced = True
			if not replaced: self._dir.append(nv)
			for i in todel: del self[i]

	def __delitem__(self, n):
		if isinstance(n, type(0)): del self._dir[n]
		elif isinstance(n, slice(0).__class__):
			# delete all <foo>s
			n = n.start
			if self._dNS and not islst(n): n = (self._dNS, n)
			
			for i in range(len(self)):
				if self[i]._name == n: del self[i]
		else:
			# delete first foo
			for i in range(len(self)):
				if self[i]._name == n: del self[i]
				break
	
	def __call__(self, *_pos, **_set): 
		if _set:
			for k in _set.keys(): self._attrs[k] = _set[k]
		if len(_pos) > 1:
			for i in range(0, len(_pos), 2):
				self._attrs[_pos[i]] = _pos[i+1]
		if len(_pos) == 1 is not None:
			return self._attrs[_pos[0]]
		if len(_pos) == 0:
			return self._attrs

	def __len__(self): return len(self._dir)

	def get(self, n):
		try:
			return self.__getitem__(n)
		except KeyError:
			return None

	def getLineNumber (self):
		return self._line

class Namespace:
	def __init__(self, uri): self.__uri = uri
	def __getattr__(self, n): return (self.__uri, n)
	def __getitem__(self, n): return (self.__uri, n)

from xml.sax.handler import EntityResolver, DTDHandler, ContentHandler, ErrorHandler

class Seeder(EntityResolver, DTDHandler, ContentHandler, ErrorHandler):
	def __init__(self, parser=None):
		if parser:
			self.getLineNumber = lambda: parser.getLineNumber ()
		else:
			self.getLineNumber = lambda: None
		self.stack = []
		self.ch = ''
		self.prefixes = {}
		ContentHandler.__init__(self)
		
	def startPrefixMapping(self, prefix, uri):
		if not self.prefixes.has_key(prefix): self.prefixes[prefix] = []
		self.prefixes[prefix].append(uri)
	def endPrefixMapping(self, prefix):
		self.prefixes[prefix].pop()
	
	def startElementNS(self, name, qname, attrs):
		ch = self.ch; self.ch = ''	
		if ch and not ch.isspace(): self.stack[-1]._dir.append(ch)

		attrs = dict(attrs)
		newprefixes = {}
		for k in self.prefixes.keys(): newprefixes[k] = self.prefixes[k][-1]
		
		self.stack.append(Element(name, attrs, prefixes=newprefixes.copy(), line=self.getLineNumber ()))
	
	def characters(self, ch):
		self.ch += ch
	
	def endElementNS(self, name, qname):
		ch = self.ch; self.ch = ''
		if ch and not ch.isspace(): self.stack[-1]._dir.append(ch)
	
		element = self.stack.pop()
		if self.stack:
			self.stack[-1]._dir.append(element)
		else:
			self.result = element

from xml.sax import make_parser
from xml.sax.handler import feature_namespaces

def seed(fileobj):
	seeder = Seeder()
	parser = make_parser()
	parser.setFeature(feature_namespaces, 1)
	parser.setContentHandler(seeder)
	parser.parse(fileobj)
	return seeder.result

def parse(text):
	from StringIO import StringIO
	return seed(StringIO(text))

def load(url): 
	import urllib
	return seed(urllib.urlopen(url))

def unittest():
	parse('<doc>a<baz>f<b>o</b>ob<b>a</b>r</baz>a</doc>').__repr__(1,1) == \
	  '<doc>\n\ta<baz>\n\t\tf<b>o</b>ob<b>a</b>r\n\t</baz>a\n</doc>'
	
	assert str(parse("<doc />")) == ""
	assert str(parse("<doc>I <b>love</b> you.</doc>")) == "I love you."
	assert parse("<doc>\nmom\nwow\n</doc>")[0].strip() == "mom\nwow"
	assert str(parse('<bing>  <bang> <bong>center</bong> </bang>  </bing>')) == "center"
	assert str(parse('<doc>\xcf\x80</doc>')) == '\xcf\x80'
	
	d = Element('foo', attrs={'foo':'bar'}, children=['hit with a', Element('bar'), Element('bar')])
	
	try: 
		d._doesnotexist
		raise "ExpectedError", "but found success. Damn."
	except AttributeError: pass
	assert d.bar._name == 'bar'
	try:
		d.doesnotexist
		raise "ExpectedError", "but found success. Damn."
	except AttributeError: pass
	
	assert hasattr(d, 'bar') == True
	
	assert d('foo') == 'bar'
	d(silly='yes')
	assert d('silly') == 'yes'
	assert d() == d._attrs
	
	assert d[0] == 'hit with a'
	d[0] = 'ice cream'
	assert d[0] == 'ice cream'
	del d[0]
	assert d[0]._name == "bar"
	assert len(d[:]) == len(d._dir)
	assert len(d[1:]) == len(d._dir) - 1
	assert len(d['bar':]) == 2
	d['bar':] = 'baz'
	assert len(d['bar':]) == 3
	assert d['bar']._name == 'bar'
	
	d = Element('foo')
	
	doc = Namespace("http://example.org/bar")
	bbc = Namespace("http://example.org/bbc")
	dc = Namespace("http://purl.org/dc/elements/1.1/")
	d = parse("""<doc version="2.7182818284590451"
	  xmlns="http://example.org/bar" 
	  xmlns:dc="http://purl.org/dc/elements/1.1/"
	  xmlns:bbc="http://example.org/bbc">
		<author>John Polk and John Palfrey</author>
		<dc:creator>John Polk</dc:creator>
		<dc:creator>John Palfrey</dc:creator>
		<bbc:show bbc:station="4">Buffy</bbc:show>
	</doc>""")

	assert repr(d) == '<doc version="2.7182818284590451">...</doc>'
	assert d.__repr__(1) == '<doc xmlns:bbc="http://example.org/bbc" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns="http://example.org/bar" version="2.7182818284590451"><author>John Polk and John Palfrey</author><dc:creator>John Polk</dc:creator><dc:creator>John Palfrey</dc:creator><bbc:show bbc:station="4">Buffy</bbc:show></doc>'
	assert d.__repr__(1,1) == '<doc xmlns:bbc="http://example.org/bbc" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns="http://example.org/bar" version="2.7182818284590451">\n\t<author>John Polk and John Palfrey</author>\n\t<dc:creator>John Polk</dc:creator>\n\t<dc:creator>John Palfrey</dc:creator>\n\t<bbc:show bbc:station="4">Buffy</bbc:show>\n</doc>'

	assert repr(parse("<doc xml:lang='en' />")) == '<doc xml:lang="en"></doc>'

	assert str(d.author) == str(d['author']) == "John Polk and John Palfrey"
	assert d.author._name == doc.author
	assert str(d[dc.creator]) == "John Polk"
	assert d[dc.creator]._name == dc.creator
	assert str(d[dc.creator:][1]) == "John Palfrey"
	d[dc.creator] = "Me!!!"
	assert str(d[dc.creator]) == "Me!!!"
	assert len(d[dc.creator:]) == 1
	d[dc.creator:] = "You!!!"
	assert len(d[dc.creator:]) == 2
	
	assert d[bbc.show](bbc.station) == "4"
	d[bbc.show](bbc.station, "5")
	assert d[bbc.show](bbc.station) == "5"

	e = Element('e')
	e.c = '<img src="foo">'
	assert e.__repr__(1) == '<e><c>&lt;img src="foo"></c></e>'
	e.c = '2 > 4'
	assert e.__repr__(1) == '<e><c>2 > 4</c></e>'
	e.c = 'CDATA sections are <em>closed</em> with ]]>.'
	assert e.__repr__(1) == '<e><c>CDATA sections are &lt;em>closed&lt;/em> with ]]&gt;.</c></e>'
	e.c = parse('<div xmlns="http://www.w3.org/1999/xhtml">i<br /><span></span>love<br />you</div>')
	assert e.__repr__(1) == '<e><c><div xmlns="http://www.w3.org/1999/xhtml">i<br /><span></span>love<br />you</div></c></e>'	
	
	e = Element('e')
	e('c', 'that "sucks"')
	assert e.__repr__(1) == '<e c="that &quot;sucks&quot;"></e>'

	
	assert quote("]]>") == "]]&gt;"
	assert quote('< dkdkdsd dkd sksdksdfsd fsdfdsf]]> kfdfkg >') == '&lt; dkdkdsd dkd sksdksdfsd fsdfdsf]]&gt; kfdfkg >'
	
	assert parse('<x a="&lt;"></x>').__repr__(1) == '<x a="&lt;"></x>'
	assert parse('<a xmlns="http://a"><b xmlns="http://b"/></a>').__repr__(1) == '<a xmlns="http://a"><b xmlns="http://b"></b></a>'
	
if __name__ == '__main__': unittest()
