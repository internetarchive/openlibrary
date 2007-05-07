#-- a wrapper around a MARC21Record, interpreting
#-- it according to the MARC 21 Format for Bibliographic Data,
#-- described here: http://www.loc.gov/marc/bibliographic/ecbdhome.html

from string import strip, join
from MARC21 import *

class MARC21BiblioExn (MARC21Exn):
        pass
 
class MARC21BiblioRecord:
	record_status_codes = {
		'a': "increased_encoding_level",
		'c': "corrected",
		'd': "deleted",
		'n': "new",
		'p': "increased_encoding_level_from_prepublication"
	}
	record_types = {
		'a': "Language material",
    		'c': "Notated music",
		'd': "Manuscript notated music",
		'e': "Cartographic material",
		'f': "Manuscript cartographic material",
		'g': "Projected medium",
		'i': "Nonmusical sound recording",
		'j': "Musical sound recording",
		'k': "Two-dimensional nonprojectable graphic",
		'm': "Computer file",
		'o': "Kit",
		'p': "Mixed material",
		'r': "Three-dimensional artifact or naturally occurring object",
		't': "Manuscript language material"
	}
	bibliographic_levels = {
		'a': "Monographic component part",
		'b': "Serial component part",
		'c': "Collection",
		'd': "Subunit",
		'i': "Integrating resource",
		'm': "Monograph/item",
		's': "Serial"
	}
	types_of_control = {
		'a': "Archival",
		' ': "No specific type"
	}
        encoding_levels = {
		' ': "Full level",
		'1': "Full level, material not examined",
		'2': "Less-than-full level, material not examined",
		'3': "Abbreviated level",
		'4': "Core level",
		'5': "Partial (preliminary) level",
		'7': "Minimal level",
		'8': "Prepublication level",
		'u': "Unknown",
		'z': "Not applicable"
	}
	descriptive_cataloging_forms = {
		' ': "Non-ISBD",
		'a': "AACR 2",
		'i': "ISBD",
		'u': "Unknown"
	}
	linked_record_requirements = {
		' ': "Related record not required",
		'r': "Related record required"
	}

        def __init__ (self, marc21_record):
                self.marc21_record = marc21_record
		if self.marc21_record.dataFields.get ("880"):
			r.warn ("has ALTERNATE GRAPHICS REPRESENTATION")

        def __getitem__ (self, key):
                extractor = MARC21BiblioRecord.__dict__.get (key)
                if not extractor:
                        raise MARC21BiblioExn ("don't know how to extract the feature called \"%s\"" % key)
                return extractor (self)
        
        def get_field (self, tag, default=None):
                return self.marc21_record.get_field (tag, default)

	def get_fields (self, tag):
		return self.marc21_record.get_fields (tag)

        def get_field_value (self, tag, default=None):
                field = self.get_field (tag, None)
                if field:
                        return str (field)
                else:
                        return default

	output_fields = (
		"marc_control_number",
		# "marc_character_coding_scheme",
                # "marc_biblio_record_status",
		# "marc_biblio_record_type",
		# "marc_biblio_bibliographic_level",
		# "marc_biblio_type_of_control",
		# "marc_biblio_encoding_level",
		# "marc_biblio_descriptive_cataloging_form",
		# "marc_biblio_linked_record_requirement",
		# "marc_biblio_language",
		"universal_decimal_class",
		"dewey_decimal_class",
		"language_code",
		"title",
		"authors",
		"edition",
		"publisher",
		"publish_place",
		"publish_date",
		"physical_format",
		"physical_extent",
		"physical_dimensions",
		"notes",
		"description",
		"subjects"
		)

        def marc_control_number (self):
                return strip (self.get_field_value ("001"))

	def marc_character_coding_scheme (self):
		return self.marc21_record.character_coding_scheme

        def marc_biblio_record_status (self):
                return self.marc21_record.record_status

	def marc_biblio_record_type (self):
		return self.marc21_record.type_of_record

	def marc_biblio_bibliographic_level (self):
		return self.marc21_record.implementation_defined1[0]

	def marc_biblio_type_of_control (self):
		return self.marc21_record.implementation_defined1[1]

	def marc_biblio_encoding_level (self):
		return self.marc21_record.implementation_defined2[0]

	def marc_biblio_descriptive_cataloging_form (self):
		return self.marc21_record.implementation_defined2[1]

	def marc_biblio_linked_record_requirement (self):
		return self.marc21_record.implementation_defined2[2]

	def marc_biblio_language (self):
		cf008 = self.get_field ("008", False)
		if not cf008:
			return None
		lang = str(cf008)[35:38]
		if lang == "|||":
			if len(self.get_fields ("041")) > 0:
				self.marc21_record.err ("has LANGUAGE CODE field")
			return None
		return lang

	def language_code (self):
		return self.marc_biblio_language ()

	def universal_decimal_class (self):
		classes = []
		for udcn in self.get_fields ("080"):
			edition_number = udcn.get_elt ("2", "?")
			classification_numbers = udcn.get_elts ("a")
			classes.extend ([ "%s:%s"%(edition_number,cn) for cn in classification_numbers ])
		return classes

	def dewey_decimal_class (self):
		classes = []
		for ddcn in self.get_fields ("082"):
			edition_number = ddcn.get_elt ("2", "?")
			classification_numbers = ddcn.get_elts ("a")
			classes.extend ([ "%s:%s"%(edition_number,cn) for cn in classification_numbers ])
		return classes
		
        def title_statement (self):
                return self.get_field ("245")

        def title (self):
                ts = self.title_statement ()
                return strip (ts.get_elt ("a") + " " + join (ts.get_elts ("b"), " "))

        def author (self):
		a = None
		pn = self.get_field ("100")
		if pn:
			name = pn.get_elt ("a", None)
			if name:
				a = { 'name': name }
				dates = pn.get_elt ("d", None)
				if dates:
					a["dates"] = dates
		else:
			ts = self.title_statement ()
			name = join (ts.get_elts ("c"), ", ")
			if name:
				a = { name: name }
		return a

	def authors (self):
		a = self.author ()
		if a: return [a]
		else: return None

        def physical_format (self):
                return self.title_statement ().get_elt ("h", None)
        
        def edition (self):
                es = self.get_field ("250")
                if not es:
                        return None
                return (strip (es.get_elt ("a", "") + " " + es.get_elt ("b", "")) or None)

        def publications (self):
                return self.get_fields ("260")

        def publish_place (self):
                return join ([ join (p.get_elts ("a"), ", ") for p in self.publications () ], ", ")

        def publisher (self):
                return join ([ join (p.get_elts ("b"), ", ") for p in self.publications () ], ", ")

        def publish_date (self):
                return join ([ join (p.get_elts ("c"), ", ") for p in self.publications () ], ", ")

	def physicals (self):
		return self.get_fields ("300")

	def physical_extent (self):
		# XXX
		extents = [ join (p.get_elts ("a"), ", ") for p in self.physicals ()]
		return join (extents, ", ")

	def physical_dimensions (self):
		dimensions = [ join (p.get_elts ("c"), ", ") for p in self.physicals ()]
		return join (dimensions, ", ")

	def notes (self):
		notes = []
		for wn in self.get_fields ("501"):
			notes.extend (wn.get_elts ("a"))
		for dn in self.get_fields ("502"):
			notes.extend (dn.get_elts ("a"))
		for fcn in self.get_fields ("505"):
			notes.extend (fcn.get_elts ("a"))
			notes.extend (fcn.get_elts ("t"))
		for sn in self.get_fields ("525"):
			notes.extend (sn.get_elts ("a"))
		for apfan in self.get_fields ("530"):
			notes.extend (apfan.get_elts ("a"))
			notes.extend (apfan.get_elts ("b"))
			notes.extend (apfan.get_elts ("c"))
			notes.extend (apfan.get_elts ("d"))
			notes.extend (apfan.get_elts ("u"))
		if len (notes) > 0:
			return join (notes, "; ")
		else:
			return None

	def description (self):
		summaries = []
		for s in self.get_fields ("520"):
			summaries.extend (s.get_elts ("a"))
			summaries.extend (s.get_elts ("b"))
		if len (summaries) > 0:
			return join (summaries, "; ")
		else:
			return None

	def subjects (self):
		subjects = []
		for pn in self.get_fields ("600"):
			subjects.append (join (pn.get_elts ("c") + pn.get_elts ("a") + pn.get_elts ("b"), " "))
		return subjects

class MARC21BiblioFile:

        def __init__ (self, input, output_fields=MARC21BiblioRecord.output_fields):
                self.marc_file = MARC21File (input)
                self.output_fields = output_fields
                self.eof = False

        def __iter__(self): return self

        def next (self):
		r = self.next_record ()
		item = {}
		for f in self.output_fields:
			v = r[f]
			if v:
				item[f] = v
		return item

        def next_record (self):
                if self.eof:
                        raise StopIteration
                marc_record = self.marc_file.next ()
                if not marc_record:
                        self.eof = True
                        raise StopIteration
                return MARC21BiblioRecord (marc_record)
