# -- read MARC21 records, yielding dictionary representations of Open Library items

from sys import stdin
from types import *
from string import strip, join
from unicodedata import normalize
from urllib import urlencode

from MARC21 import *
from MARC21Biblio import *
from catalog.lang import *
from catalog.schema import schema

record_id_delimiter = ":"

def parser (file, file_locator, source_id):
    if (source_id.find (record_id_delimiter) >= 0):
        die ("the source id '%s' contains the record id delimiter '%s'" % (source_id, record_id))
    f = MARC21BiblioFile (file)
    try:
        while True:
            try:
                record = f.next()
                item = distill_record (record, file_locator, source_id)
                yield item
            except MARC21Exn, e:
                warn ("couldn't parse record: %s" % e)
    except StopIteration:
        pass

def urlencode_record_locator (r, file_locator):
    return urlencode ({ 'file': file_locator,
                        'offset': r.record_pos (),
                        'length': r.record_len () })

def distill_record (r, file_locator, source_id):
    edition = {}
    edition['source_record_loc'] = [urlencode_record_locator (r, file_locator)]
    edition['source_record_id'] = [record_id_delimiter.join ([source_id,
                                                              strip (r.get_field_value ('003')),
                                                              strip (r.get_field_value ('001'))])]
    for (field_name, field_spec) in schema['edition'].iteritems ():
        marc_specs = field_spec.get ('marc_fields')
        multiple = (field_spec.get ('count', "single") == "multiple")
        if marc_specs:
            if (type (marc_specs) != list):
                marc_specs = [marc_specs]
            for marc_spec in marc_specs:
                marc_value_producer = compile_marc_spec (marc_spec)
                field_values = (marc_value_producer and list (marc_value_producer (r))) or []
                if (len (field_values) > 1 and not multiple):
                    raise Error ("record %s: multiple values from MARC data for single-valued OL field '%s'" % (field_name, display_record_locator (r, file_locator)))
                if (len (field_values) > 0):
                    edition[field_name] = (multiple and field_values) or field_values[0];
    return edition

re_spaces = re.compile (r'\s+')
re_codespec = re.compile (r'(\d\d\d):([a-z]+)')

def field_producer (field, subfields):
        def generator (r):
            ff = r.get_fields (field)
            for f in ff:
                def subfield_data (sf):
                    return " ".join (map (unicode_to_utf8, f.get_elts (sf)))
                yield " ".join (map (subfield_data, subfields))
        return generator

def compile_marc_spec (spec):
    terms = re_spaces.split (spec)
    if (len (terms) == 1):
        m = re_codespec.match (terms[0])
        if m:
            field = m.group (1)
            subfields = list (m.group (2))
            return field_producer (field, subfields)
    return None

def unicode_to_utf8 (u):
        nu = normalize ('NFKC', u)
        return nu.encode ('utf8')

### authors

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

### filters, referenced from the schema

re_isbn_chars = re.compile (r'^([\dX]+)')

def clean (s):
    return strip (s, " /.,;:")

def clean_name (s):
    return strip (s, " /,;:")

def normalize_isbn (s):
    m = re_isbn_chars.match (s)
    if m:
        isbn_chars = m.group (1)
        if (len (isbn_chars) == 13):
            return isbn_chars
        else:
            if (len (isbn_chars) == 10):
                return isbn_10_to_isbn_13 (isbn_10)
            else:
                warn ("bad ISBN: '%s'" % isbn_chars)
    return None

## don't give empty string values in items
#
# def next (self):
#   r = self.next_record ()
#   item = {}
#   for f in self.output_fields:
#       v = r[f]
#       if (isinstance (v, StringTypes) and v) or v is not None:
#           item[f] = v
#   return item

## check for language code field?
#
#       if lang == "|||":
#           if len(self.get_fields ("041")) > 0:
#               self.marc21_record.err ("has LANGUAGE CODE field")

## is "edition number" important for dewey decimal classification?
#
#   def dewey_decimal_class (self):
#       classes = []
#       for ddcn in self.get_fields ("082"):
#           edition_number = ddcn.get_elt ("2", "?")
#           classification_numbers = ddcn.get_elts ("a")
#           classes.extend ([ "%s:%s"%(edition_number,cn) for cn in classification_numbers ])
#       return classes

if __name__ == "__main__":
    source_id = sys.argv[1]
    file_locator = sys.argv[2]
    for item in parser (sys.stdin, file_locator, source_id):
        print ""
        print item['source_record_loc'][0]
        print item
