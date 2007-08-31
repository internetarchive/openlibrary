# provides a parser from ONIX files to Open Library items

import re
import sys
import os
from types import *
from lang import *

import xml.sax
from xml.sax.handler import *
from xml.sax.saxutils import prepare_input_source

from thread_utils import AsyncChannel, threaded_generator
from onix import OnixProduct, OnixHandler, onix_codelists

def parser (input):
	# returns a generator that produces dicts representing Open Library items

	def produce_items (produce):
		source = prepare_input_source (input)

		parser = xml.sax.make_parser ()
		parser.setFeature (xml.sax.handler.feature_namespaces, 1)
		parser.setContentHandler (OnixHandler (parser, process_product))
		url_cache_dir = os.getenv ("URL_CACHE_DIR")
		if url_cache_dir:
			sys.stderr.write ("using url cache in %s\n" % url_cache_dir)
			parser.setEntityResolver (CachingEntityResolver (parser, url_cache_dir))
		else:
			sys.stderr.write ("no url_cache_dir; XML resources will always be loaded from network\n")
		parser.setErrorHandler (MyErrorHandler ())
		parser.parse (source)

	return threaded_generator (produce_items, 50)

def process_product (p):
	op = OnixProduct (p)	# the incoming record
	o = {}			# the Open Library item we're producing

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
			type_name = str (OnixProduct.pi_type_name (pi_type)).replace ("-", "_")
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
			role = OnixProduct.contributor_role (role_code)
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
			# 	fmt = onix_codelists["List55"][fmt_code]
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

class MyErrorHandler:
	def error (self, exn):
		raise exn
	def fatalError (self, exn):
		raise exn
	def warning (self, exn):
		sys.stderr.write ("warning: %s\n" % exn.getMessage)

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

