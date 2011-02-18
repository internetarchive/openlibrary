"""Generic utilities"""

from urllib import quote_plus
import re

to_drop = set(''';/?:@&=+$,<>#%"{}|\\^[]`\n\r''')

def str_to_key(s):
    return ''.join(c if c != ' ' else '_' for c in s.lower() if c not in to_drop)

def url_quote(s):
    return quote_plus(s.encode('utf-8')) if s else ''

re_isbn = re.compile('^([0-9]{9}[0-9Xx]|[0-9]{13})$')
def read_isbn(s): # doesn't validate checksums
    s = s.replace('-', '')
    return s if re_isbn.match(s) else None

