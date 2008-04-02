#-- a wrapper around a MARC21Record, interpreting
#-- it according to the MARC 21 Format for Bibliographic Data,
#-- described here: http://www.loc.gov/marc/bibliographic/ecbdhome.html

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
			marc21_record.warn ("has ALTERNATE GRAPHICS REPRESENTATION")

	def record_pos (self):
		return self.marc21_record.file_pos

	def record_len (self):
		return len (self.marc21_record.raw_data)

        def get_field (self, tag, default=None):
                return self.marc21_record.get_field (tag, default)

	def fields (self):
		return self.marc21_record.fields ()

	def get_fields (self, tag):
		return self.marc21_record.get_fields (tag)

        def get_field_value (self, tag, default=None):
                field = self.get_field (tag, None)
                if field:
                        return str (field)
                else:
                        return default

        def marc_control_number (self):
                return self.get_field_value ("001")

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

class MARC21BiblioFile:

        def __init__ (self, input):
                self.marc_file = MARC21File (input)
                self.eof = False

        def __iter__(self): return self

        def next (self):
                if self.eof:
                        raise StopIteration
                marc_record = self.marc_file.next ()
                if not marc_record:
                        self.eof = True
                        raise StopIteration
                return MARC21BiblioRecord (marc_record)
