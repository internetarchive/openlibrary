from normalize import normalize
from time import time
import re

def add_to_index(dbm, key, edition_key):
    if not key:
        return
    try:
        key = str(key)
    except UnicodeEncodeError:
        return
    if key in dbm:
        dbm[key] += ' ' + edition_key
    else:
        dbm[key] = edition_key

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

def record_to_dbm(record, dbm):
    def callback(field, value, key):
        add_to_index(dbm[field], value, key)
    read_record(record, callback)

def read_record(record, callback):
    if 'title' not in record or record['title'] is None:
        return
    if 'subtitle' in record and record['subtitle'] is not None:
        title = record['title'] + ' ' + record['subtitle']
    else:
        title = record['title']
    key = record['key']
    callback('title', short_title(title), key)
    if 'title_prefix' in record and record['title_prefix'] is not None:
        title2 = short_title(record['title_prefix'] + title)
        callback('title', title2, key)

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
            if not v:
                continue
            if clean:
                v = clean(v)
                if not v:
                    continue
            callback(b, v, key)

def test_read_record():
    def empty_dbm():
        return dict((i, {}) for i in ('lccn', 'oclc', 'isbn', 'title'))

    dbm = empty_dbm()

    line = '{"title_prefix": null, "subtitle": null, "description": null, "language": null, "title": "Metamagical Themas", "by_statement": null, "notes": null, "language_code": null, "id": 9888119, "edition_name": null, "publish_date": null, "key": "/b/OL7254007M", "authors": [{"key": "/a/OL2621476A"}], "ocaid": null, "type": "/type/edition", "coverimage": null}'
    line = line.replace('null', 'None')
    record = eval(line)
    read_record(record, dbm)
    assert dbm == { 'lccn': {}, 'isbn': {}, 'oclc': {}, 'title': {'metamagical themas': '9888119'} }

    record = {"pagination": "8, 304 p.", "description": "Test", "title": "Kabita\u0304.", "lccn": ["sa 64009056"], "notes": "Bibliographical footnotes.\r\nIn Oriya.", "number_of_pages": 304, "languages": [{"key": "/l/ori"}], "authors": [{"key": "/a/OL1A"}], "lc_classifications": ["PK2579.R255 K3"], "publish_date": "1962", "publish_country": "ii ", "key": "/b/OL1M", "language_code": "304", "coverimage": "/static/images/book.trans.gif", "oclc_numbers": ["31249133"], "type": "/type/edition", "id": 96}
    dbm = empty_dbm()
    read_record(record, dbm)
    assert dbm == {'lccn': {'64009056': '96'}, 'isbn': {}, 'oclc': {'31249133': '96'}, 'title': {'kabitau0304': '96'}}
