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

def parser (file, file_locator=None):
    f = MARC21BiblioFile (file)
    try:
        while True:
            try:
                record = f.next()
                item = distill_record (record, file_locator)
                yield item
            except MARC21Exn, e:
                warn ("couldn't parse record: %s" % e)
    except StopIteration:
        pass

def display_record_locator (r, file_locator):
    return urlencode ({ 'file': file_locator or "?",
                        'offset': r.record_pos (),
                        'length': r.record_len () })

def distill_record (r, file_locator):
    edition = {}
    for (field_name, field_spec) in schema['edition'].iteritems ():
        marc_specs = field_spec.get ('marc_fields')
        multiple = (field_spec.get ('count', "single") == "multiple")
        if marc_specs:
            if (type (marc_specs) != list):
                marc_specs = [marc_specs]
            for marc_spec in marc_specs:
                marc_value_producer = compile_marc_spec (marc_spec)
                field_values = list (marc_value_producer (r))
                if (len (field_values) > 1 and not multiple):
                    raise Error ("record %s: multiple values from MARC data for single-valued OL field '%s'" % (field_name, display_record_locator (r, file_locator)))
                if (len (field_values) > 0):
                    edition[field_name] = (multiple and field_values) or field_values[0];
    return edition

def compile_marc_spec (spec):
    def producer (r):
        yield "VAL"
    return producer

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
    for item in parser (sys.stdin):
        print item
