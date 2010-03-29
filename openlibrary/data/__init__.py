"""Library for managing Open Library data"""

import simplejson
import re

def parse_data_table(filename):
    """Parses the dump of data table and returns an iterator with 
    <key, type, revision, json> for all entries.
    """
    for line in open(filename):
        thing_id, revision, json = pgdecode(line).strip().split("\t")
        d = simplejson.loads(json)
        yield d['key'], d['type']['key'], d['revision'], json

def _make_sub(d):
    """Make substituter.

        >>> f = _make_sub(dict(a='aa', bb='b'))
        >>> f('aabbb')
        'aaaabb'
    """
    def f(a):
        return d[a.group(0)]
    rx = re.compile("|".join(map(re.escape, d.keys())))
    return lambda s: s and rx.sub(f, s)

def _invert_dict(d):
    return dict((v, k) for (k, v) in d.items())

_pgencode_dict = {'\n': r'\n', '\r': r'\r', '\t': r'\t', '\\': r'\\'}
_pgencode = _make_sub(_pgencode_dict)
_pgdecode = _make_sub(_invert_dict(_pgencode_dict))

def pgencode(text):
    """Reverse of pgdecode."""
    return _pgdecode(text)

def pgdecode(text):
    r"""Decode postgres encoded text.
        
        >>> pgdecode('\\n')
        '\n'
    """
    return _pgdecode(text)

