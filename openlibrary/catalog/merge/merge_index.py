# build a merge database from JSON dump

import re
from normalize import normalize

def short_title(s):
    return normalize(s)[:25]

re_letters = re.compile('[A-Za-z]')

def clean_lccn(lccn):
    return re_letters.sub('', lccn).strip()

re_isbn = re.compile('([-0-9X]{10,})')

def clean_isbn(isbn):
    m = re_isbn.search(isbn)
    if m:
        return m.group(1).replace('-', '')



def add_to_indexes(record):
    if 'title' not in record or record['title'] is None:
        return
    if 'subtitle' in record and record['subtitle'] is not None:
        title = record['title'] + ' ' + record['subtitle']
    else:
        title = record['title']
    title1 = short_title(title)
    yield 'title', title1
    if 'title_prefix' in record and record['title_prefix'] is not None:
        title2 = short_title(record['title_prefix'] + title)
        if title1 != title2:
            yield 'title', title2

    fields = [
        ('lccn', 'lccn', clean_lccn),
        ('oclc_numbers', 'oclc', None),
        ('isbn_10', 'isbn', clean_isbn),
        ('isbn_13', 'isbn', None),
    ]
    for a, b, clean in fields:
        if a not in record:
            continue
        for v in record[a]:
            if not v or b=='isbn' and len(v) < 10:
                continue
            if clean:
                v = clean(v)
                if not v:
                    continue
            yield b, v
