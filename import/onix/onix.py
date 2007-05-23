import re
import sys
import os
from types import *
from lang import *

import xml.sax
from xml.sax.handler import *
from xml.sax.saxutils import prepare_input_source
import xmltramp

from thread_utils import AsyncChannel, threaded_generator
from sax_utils import *

repo_path = os.getenv ("PHAROS_REPO")
codelists_path = "%s/%s" % (repo_path, "import/onix/ONIX_BookProduct_CodeLists.xsd")
ref_dtd_path = "%s/%s" % (repo_path, "import/onix/ONIX_BookProduct_Release2.1_reference.xsd")

def parser (input):

	def produce_items (produce):
		OnixProduct.load_shortnames (ref_dtd_path)

		source = prepare_input_source (input)

		parser = xml.sax.make_parser ()
		parser.setFeature (xml.sax.handler.feature_namespaces, 1)
		parser.setContentHandler (OnixHandler (parser, produce))
		url_cache_dir = os.getenv ("URL_CACHE_DIR")
		if url_cache_dir:
			sys.stderr.write ("using url cache in %s\n" % url_cache_dir)
			parser.setEntityResolver (CachingEntityResolver (parser, url_cache_dir))
		else:
			sys.stderr.write ("no url_cache_dir; XML resources will always be loaded from network\n")
		parser.setErrorHandler (MyErrorHandler ())
		parser.parse (source)

	return threaded_generator (produce_items, 50)

class MyErrorHandler:
	def error (self, exn):
		raise exn
	def fatalError (self, exn):
		raise exn
	def warning (self, exn):
		sys.stderr.write ("warning: %s\n" % exn.getMessage)

class OnixProduct:
	# note: this only works when using the "short" names of elements
	# should check that the document uses the short DTD, and if not,
	# use the reference names to access field values.

	def __init__ (self, p):
		self.p = p

	@staticmethod
	def reify_child (v):
		if len (v._dir) == 1 and isinstance (v._dir[0], StringTypes):
			return v._dir[0]
		else:
			return OnixProduct (v)

	def __getitem__ (self, n):
		slicing = False
		if isinstance (n, SliceType):
			slicing = True
			reference_name = n.start
		else:
			reference_name = n
		name = OnixProduct.get_shortname (reference_name) # or reference_name.lower ()
		values = self.p[name:]
		if slicing:
			return map (OnixProduct.reify_child, values)
		else:
			if len (values) == 0:
				raise KeyError ("no value for %s (%s)" % (reference_name, name))
			elif len (values) > 1:
				raise Exception ("more than one value for %s (%s)" % (reference_name, name))
			return OnixProduct.reify_child (values[0])

	def get (self, n):
		try:
			return self.__getitem__ (n)
		except KeyError:
			return None

	def getLineNumber (self):
		return self.p.getLineNumber ()

	def __unicode__ (self):
		return self.p.__unicode__ ()

	def __str__ (self):
		return self.__unicode__ ()

	shortnames = None

	@staticmethod
	def get_shortname (reference_name):
		try:
			return OnixProduct.shortnames[reference_name]
		except KeyError:
			raise Exception ("unknown reference name: %s" % reference_name)

	@staticmethod
	def load_shortnames (path):
		def schema (name, attrs):
			def element (name, attrs):
				def typespec (name, attrs):
					def attribute (name, attrs):
						if (attrs.getValueByQName ('name') == "shortname"):
							shortname = attrs.getValueByQName ('fixed')
							return CollectorValue (shortname)
						else:
							return CollectorNone ()
					return NodeCollector ({ 'attribute': attribute, collector_any: typespec })
				elt_name = attrs.getValueByQName ('name')
				return NamedCollector (elt_name, { collector_any: typespec })
			return DictCollector ({ 'element': element })
		if not OnixProduct.shortnames:
			f = open (path, "r")
			OnixProduct.shortnames = collector_parse (f, { 'schema': schema })
			f.close ()

record_no = 0

class OnixHandler (ContentHandler):

	def __init__ (self, parser, receiver):
		self.parser = parser
		self.receiver = receiver
		self.subhandler = None
		self.codelists = parse_codelists (open (codelists_path, "r"))
		ContentHandler.__init__ (self)

	def process_product (self, p):
		op = OnixProduct (p)
		o = {}
		global record_no
		o["source_record_pos"] = record_no; # XXX
		record_no += 1

		# record id
		o['source_record_lineno'] = p.getLineNumber ()

		# title, subtitle
		tt = [ t for t in op["Title":] if t["TitleType"] == '01' ]
		if len (tt) > 1:
			raise Exception ("more than one distinctive title")
		elif len(tt) == 0:
			raise Exception ("no distinctive title")
		t = tt[0]
		prefix = t.get ("TitlePrefix")
		if prefix:
			prefix = prefix.strip ()
			o['title_prefix_len'] = len (prefix) + 1  # prefix plus space
			o['title'] = prefix + " " + t["TitleWithoutPrefix"].strip ()
		else:
			title = t.get ("TitleText")
			if title:
				o['title'] = title
		subtitle = t.get ("Subtitle")
		if subtitle:
			o['subtitle'] = subtitle

		# id codes (ISBN, etc.)
		for pi in op["ProductIdentifier":]:
			pi_type = pi["ProductIDType"]
			pi_val = pi["IDValue"]
			if pi_type != '01':
				type_name = str (self.pi_type_name (pi_type)).replace ("-", "_")
				o[type_name] = pi_val

		# author, contributors
		for c in op["Contributor":]:
			role_codes = c["ContributorRole":]
			role_codes.sort ()
			role_code = role_codes[0]

			name = person_name (c)
			if not name:
				warn ("=====> no name for contributor at line %d" % c.getLineNumber ())
				continue

			if role_code != 'A01':
				role = self.contributor_role (role_code)
				add_val (o, "contributions", role + ": " + name)
				continue

			author = {}
			author["name"] = name
			add_val (o, "authors", author)

			# iname = c.get ("PersonNameInverted")
			# if iname:
			# 	author["inverted_name"] = iname
			# 	# XXX else construct inverted name from name parts

			pnis = c["PersonNameIdentifier":]
			if len (pnis) > 0:
				warn ("got PersonNameIdentifier(s): %s" % pnis[0]["IDValue"])

			# other_names = c["Name":]
			# XX: for pseudonyms, etc. ... should stash this somewhere

			for pdate in c["PersonDate":]:
				role = pdate["PersonDateRole"]
				# fmt = None
				# fmt_code = pdate.get ("DateFormat")
				# if fmt_code:
				# 	fmt = self.codelists["List55"][fmt_code]
				date = pdate["Date"]
				if role == "007": author["birth_date"] = date
				elif role == "008": author["death_date"] = date
				else: die ("bad date role: %s" % role)

			bio = c.get ("BiographicalNote")
			if bio:
				author["bio"] = bio

			# website
			# country
			# region

		contrib = op.get ("ContributorStatement")
		if not o.get ("authors"):
			# XXX: shouldn't do this: the ContributorStatement could have anything in it
			# ... but this is the only way to get author names for one of the catalogs
			if contrib:
				author = {}
				author["name"] = re_by.sub ('', contrib)
				add_val (o, "authors", author)

		# edition
		ed_type = op.get ("EditionTypeCode")
		if ed_type:
			o["edition_type"] = self.codelists["List21"][ed_type][0]
		ed_number = op.get ("EditionNumber")
		if ed_number:
			ed_vers_num = op.get ("EditionVersionNumber")
			if ed_vers_num:
				ed_number += "-" + ed_vers_num
			o["edition_number"] = ed_number
		edition = op.get ("EditionStatement")
		if edition:
			o["edition"] = edition

		# format
		format = op.get ("ProductFormDescription")
		if format:
			o["physical_format"] = format
		npages = op.get ("NumberOfPages")
		if npages:
			o["number_of_pages"] = npages
		nillus = op.get ("NumberOfIllustrations")
		if nillus:
			o["number_of_illustrations"] = nillus
		ill_note = op.get ("IllustrationsNote")
		if ill_note:
			add_val (o, "notes", ill_note)
		# see also <illustrations> composite

		# dimensions

		# language
		# (see also <language> composite)
		lang_code = op.get ("LanguageOfText")
		if lang_code:
			o["language_code"] = lang_code
			o["language"] = self.codelists["List74"][lang_code][0]

		# subject
		bisac = op.get ("BASICMainSubject")
		if bisac:
			add_val (o, "BISAC_subject_categories", bisac)
		for subject in op["Subject":]:
			scheme = subject.get ("SubjectSchemeIdentifier")
			if scheme and scheme == "10":
				code = subject.get ("SubjectCode")
				if code:
					add_val (o, "BISAC_subject_categories", code)

		# description
		for text in op["OtherText":]:
			# type = text["TextTypeCode"]
			format = text["TextFormat"]
			if format not in ("00", "02", "07"): # ASCII, HTML, Basic ASCII
				raise Exception ("unsupported description format: %s" % self.codelists["List34"][format][0])
			if o.get ("description"):
				o["description"] += "\n" + text["Text"]
			else:
				o["description"] = text["Text"]
		if not o.get ("description"):
			descr = op.get ("MainDescription")
			if descr:
				o["description"] = descr

		self.receiver (o)

		# publisher
		for pub in op["Publisher":]:
			role = pub.get ("PublishingRole")
			if role is None or role == "01":
				name = pub.get ("PublisherName")
				if name:
					o["publisher"] = name
				break
		if not o.get ("publisher"):
			pub = op.get ("PublisherName")
			if pub:
				o["publisher"] = pub

		# imprint
		imprint = op.get ("Imprint")
		if imprint:
			name = imprint.get ("ImprintName")
			if name:
				o["imprint"] = name
		if not o.get ("imprint"):
			imprint = op.get ("ImprintName")
			if imprint:
				o["imprint"] = imprint

		# publish_status
		pstat = op.get ("PublishingStatus")
		if pstat and pstat != "??":
			status = self.codelists["List64"][pstat][0]
			pstatnote = op.get ("PublishingStatusNote")
			if pstatnote:
				stats += ": " + pstatnote
			o["publish_status"] = status

		# publish_date
		pdate = op.get ("PublicationDate")
		if pdate:
			o["publish_date"] = pdate # YYYY[MM[DD]]
			# XXX: need to convert

	def pi_type_name (self, code):
		return self.codelists["List5"][code][0]

	def contributor_role (self, code):
		return self.codelists["List17"][code][0]

	def startElementNS (self, name, qname, attrs):
		if self.subhandler:
			self.subhandler.startElementNS (name, qname, attrs)
			self.subdepth += 1
		else:
			(uri, localname) = name
			if localname == "product":
				self.subhandler = xmltramp.Seeder (self.parser)
				self.subhandler.startElementNS (name, qname, attrs)
				self.subdepth = 1

	def endElementNS (self, name, qname):
		if self.subhandler:
			self.subhandler.endElementNS (name, qname)
			self.subdepth -= 1
			if self.subdepth == 0:
				self.process_product (self.subhandler.result)
				self.subhandler = None

	def characters (self, content):
		if self.subhandler:
			self.subhandler.characters (content)

name_parts = ["TitlesBeforeNames", "NamesBeforeKey", "PrefixToKey", "KeyNames", "NamesAfterKey", "SuffixToKey"]
def person_name (x):
	global name_parts
	name = x.get ("PersonName")
	if not name:
		parts = [ p for p in map (lambda p: x.get (p), name_parts) if p ]
		name = " ".join (parts)
	if not name:
		iname = x.get ("PersonNameInverted")
		if iname:
			# XXX this often works, but is not reliable;
			# shouldn't really mess with unstructured names
			m = re_iname.match (iname)
			if m:
				name = m.group (2) + " " + m.group (1)
			else:
				name = iname
	if not name:
		name = x.get ("CorporateName")
	return name

def elt_get (e, tag, reference_name):
       ee = e.get (tag) or e.get (reference_name.lower ())
       if ee:
               return unicode (ee)
       else:
               return None

re_by = re.compile ("^\s*by\s+", re.IGNORECASE)
re_iname = re.compile ("^(.*),\s*(.*)$")

def add_val (o, key, val):
	if val is not None:
		o.setdefault (key, []).append (val)

def parse_codelists (input):
	def schema (name, attrs):
		def simpleType (name, attrs):
			def restriction (name, attrs):
				def enumeration (name, attrs):
					def annotation (name, attrs):
						def documentation (name, attrs):
							return TextCollector ()
						return ListCollector ({ 'documentation': documentation })
					return NamedCollector (attrs.getValueByQName (u'value'), { 'annotation': annotation })
				return DictCollector ({ 'enumeration': enumeration })
			return NamedCollector (attrs.getValueByQName (u'name'), { 'restriction': restriction })
		return DictCollector ({ 'simpleType': simpleType })
	return collector_parse (input, { 'schema': schema })


