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
record_loc_delimiter = ":"

marc_value_generators = {}

def parser (file, file_locator, source_id):
    if (source_id.find (record_id_delimiter) >= 0):
        die ("the source id '%s' contains the record-id delimiter '%s'" % (source_id, record_id_delimiter))
    if (file_locator.find (record_loc_delimiter) >= 0):
        die ("the file locator '%s' contains the record-locator delimiter '%s'" % (file_locator, record_loc_delimiter))

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

def encode_record_locator (r, file_locator):
    return record_loc_delimiter.join ([file_locator, str (r.record_pos ()), str (r.record_len ())])

def urlencode_record_locator (r, file_locator):
    return urlencode ({ 'file': file_locator,
                        'offset': r.record_pos (),
                        'length': r.record_len () })

def distill_record (r, file_locator, source_id):
    edition = {}
    edition['source_record_loc'] = [encode_record_locator (r, file_locator)]
    edition['source_record_id'] = [record_id_delimiter.join ([source_id,
                                                              strip (r.get_field_value ('003')),
                                                              strip (r.get_field_value ('001'))])]
    for (field_name, field_spec) in schema['edition'].iteritems ():
        multiple = (field_spec.get ('count', "single") == "multiple")
        field_values = []
        marc_value_generator = marc_value_generators.get (field_name)
        if marc_value_generator:
            field_values = [ normalize_string (s) for s in marc_value_generator (r) ]
            field_values = list (set (field_values))  # remove duplicates
        if (len (field_values) > 1 and not multiple):
            die ("record %s: multiple values from MARC data for single-valued OL field '%s'" %
                 (urlencode_record_locator (r, file_locator), field_name))
        if (len (field_values) > 0):
            edition[field_name] = (multiple and field_values) or field_values[0];
    return edition

def initialize_marc_value_generators ():
    for (field_name, field_spec) in schema['edition'].iteritems ():
        marc_specs = field_spec.get ('marc_fields')
        if marc_specs:
            if (type (marc_specs) != list):
                marc_specs = [marc_specs]
            marc_value_generators[field_name] = compile_marc_specs (marc_specs)

def compile_marc_specs (specs):
    generators = map (compile_marc_spec, specs)
    def generator (r):
        for g in generators:
            for v in g (r):
                yield v
    return generator

re_spaces = re.compile (r'\s+')
re_literal = re.compile (r'"([^"]*)"')
re_field = re.compile (r'(\d\d\d):(\S+)')
re_procedure = re.compile (r'[^\d"].*')

def null_generator (r):
    if 0: yield None

def literal_generator (s):
    def gen (r):
        yield s
    return gen

def compile_marc_spec (spec):
    def spec_die (msg):
        die ("in marc spec '%s': %s" % (spec, msg))

    terms = [ t for t in re_spaces.split (spec) if t ]

    vals = []   # a stack of value generators
    def push (v):
        vals[0:0] = [v]
    def pop (n=1):
        vv = vals[0:n]
        del vals[0:n]
        return vv

    for term in terms:
        match_literal = re_literal.match (term)
        match_field = re_field.match (term)
        if match_literal:
            s = match_literal.group (1)
            push (literal_generator (s))
        elif match_field:
            field = match_field.group (1)
            subfield_spec = match_field.group (2)
            push (field_generator (field, subfield_spec))
        else:
            proc = compile_procedure (term)
            if proc:
                func = proc['func']
                nargs = proc['nargs']
                if (len (vals) < nargs):
                    spec_die ("procedure '%s' expects %d arguments but only %d remain" %
                              (term, nargs, len (vals)))
                args = pop (nargs)
                push (call_generator (func, args))
            else:
                warn ("unknown procedure '%s' will consume all available arguments and produce no values" % term)
                vals = []
                push (null_generator)

    if len (vals) > 1:
        spec_die ("there are too many values here")
    if len (vals) < 1:
        spec_die ("there are no values to produce here")
    value_generator = vals[0]
    return value_generator

procedures = {
    '+': (2, (lambda s1, s2: s1 + s2))
    }

def compile_procedure (name):
    info = procedures.get (name)
    if info:
        return { 'nargs': info[0], 'func': info[1] }
    else:
        return None

def call_generator (f, arg_generators):
    def value_generator (r):
        def generate_arglists (arg_gens):
            # generate the cross-product of the values generated by each arg_generator
            if (len (arg_gens) == 1):
                for a in arg_gens[0](r):
                    yield [a]
            elif (len (arg_gens) > 1):
                rest_lists = list (generate_arglists (arg_gens[1:]))  # don't re-generate these values
                for a in arg_gens[0](r):
                    for rest_list in rest_lists:
                        yield [a] + rest_list
        for arglist in generate_arglists (arg_generators):
            arglist.reverse ()
            val = f (*arglist)
            if val is not None:
                yield val
    return value_generator

re_subfields_exact = re.compile (r'[a-z]+')
re_subfields_range = re.compile (r'([a-z])-([a-z])')
re_positions = re.compile (r'(\d+)-(\d+)')

def field_generator (fieldname, subfield_spec):

    def code_chars_generator (start, end):
        assert isControlFieldTag (fieldname)
        assert start < end
        def gen (r):
            for f in r.get_fields (fieldname):
                yield str(f)[start:end+1]
        return gen

    def subfields_generator (subfields_lister):
        def gen (r):
            for f in r.get_fields (fieldname):
                def subfield_data (sf):
                    return " ".join ([ s for s in [ strip (ss) for ss in f.get_elts (sf) ] if s ])
                subfields = subfields_lister (f)
                fval = " ".join ([ s for s in map (subfield_data, subfields) if s ])
                if fval:
                    yield fval
        return gen

    if (isControlFieldTag (fieldname)):
        m = re_positions.match (subfield_spec)
        if m:
            start = int (m.group (1))
            end = int (m.group (2))
            return code_chars_generator (start, end)
        else:
            warn ("in field '%s', the subfield spec '%s' is ill-formed; ignoring" % (fieldname, subfield_spec))
            return null_generator
    else:
        if re_subfields_exact.match (subfield_spec):
            subfields_exact = list (subfield_spec)
            subfields_lister = lambda f: subfields_exact
            return subfields_generator (subfields_lister)
        m = re_subfields_range.match (subfield_spec)
        if m:
            low = m.group (1)
            hi = m.group (2)
            if low > hi:
                die ("subfield range '%s' is ill-formed" % subfield_spec)
            subfields_lister = lambda f: [ s for s in f.subfields () if (s >= low and s <= hi) ]
            return subfields_generator (subfields_lister)
        warn ("in field '%s', couldn't parse subfield spec '%s'; will produce no values" % (fieldname, subfield_spec))
        return null_generator

def unicode_to_utf8 (u):
    nu = normalize ('NFKC', u)
    return nu.encode ('utf8')

def normalize_string (s):
    if (type (s) is StringType):
        return s
    elif (type (s) is UnicodeType):
        return unicode_to_utf8 (s)
    else:
        die ("normalize_string called on non-string: %s" % s)

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

procedures['clean'] = (1, clean)

def clean_name (s):
    return strip (s, " /,;:")

procedures['clean_name'] = (1, clean_name)

def normalize_isbn (s):
    m = re_isbn_chars.match (s)
    if m:
        isbn_chars = m.group (1)
        if (len (isbn_chars) == 13):
            return isbn_chars
        else:
            if (len (isbn_chars) == 10):
                # return isbn10_to_isbn13 (isbn_10) XXXXXXXXXXXX
                return None
            else:
                warn ("bad ISBN: '%s'" % isbn_chars)
    return None

procedures['normalize_isbn'] = (1, normalize_isbn)

re_digits = re.compile (r'\d\d+')

def biggest_decimal (s):
    nums = re_digits.findall (s)
    if (len (nums) > 0):
        return max (nums)
    else:
        return None

procedures['biggest_decimal'] = (1, biggest_decimal)

re_lccn = re.compile (r'(...\d+).*')

def normalize_lccn (s):
    m = re_lccn.match (s)
    if m:
        return m.group (1)
    else:
        warn ("bad LCCN: '%s'" % s)
        return None

procedures['normalize_lccn'] = (1, normalize_lccn)

re_author_id_parts = re.compile (r'\w+', re.UNICODE)

def author_id (s):
    parts = [ p.lower() for p in re_author_id_parts.findall (s) ]
    return " ".join (parts)

procedures['author_id'] = (1, author_id)

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

initialize_marc_value_generators ()

if __name__ == "__main__":
    source_id = sys.argv[1]
    file_locator = sys.argv[2]
    for item in parser (sys.stdin, file_locator, source_id):
        print ""
        print item['source_record_loc'][0]
        print item
