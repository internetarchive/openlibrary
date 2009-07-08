from olwrite import Infogami, add_to_database
import web, dbhash
from read_rc import read_rc
import cjson, re, sys
from time import time

def commify(n):
    """
Add commas to an integer `n`.
 
>>> commify(1)
'1'
>>> commify(123)
'123'
>>> commify(1234)
'1,234'
>>> commify(1234567890)
'1,234,567,890'
>>> commify(None)
>>>
"""
    if n is None: return None
    r = []
    for i, c in enumerate(reversed(str(n))):
        if i and (not (i % 3)):
            r.insert(0, ',')
        r.insert(0, c)
    return ''.join(r)

def count_books():
    rows = list(web.query("select count(*) as num from thing where type=52"))
    return rows[0].num

def count_fulltext():
    rows = list(web.query("select count(*) as num from edition_str where key_id=40"))
    return commify(rows[0].num)

def get_macro():
    rows = list(web.query("select data from data, thing where thing_id=thing.id and key='/macros/BookCount' and revision=latest_revision"))
    return cjson.decode(rows[0].data)['macro']['value']

rc = read_rc()
web.config.db_parameters = dict(dbn='postgres', db=rc['db'], user=rc['user'], pw=rc['pw'], host=rc['host'])
web.config.db_printing = False
web.ctx.ip = '127.0.0.1'
web.load()

book_count = count_books()
open('/home/edward/book_count', 'a').write("%d %d\n" % (time(), book_count))

infogami = Infogami(rc['infogami'])
infogami.login('edward', rc['edward'])

macro = get_macro()
re_books = re.compile(r'books = "<strong>[\d,]+</strong>"')
books = commify(book_count)
macro = re_books.sub('books = "<strong>' + books + '</strong>"', macro)

# full text count is disabled so that the number stays about 1 million
# fulltext = count_fulltext()
# re_fulltext = re.compile(r'fulltext = "<strong>[\d,]+</strong>"')
# macro = re_fulltext.sub('fulltext = "<strong>' + fulltext + '</strong>"', macro)

q = {
    'key': '/macros/BookCount',
    'macro': { 'connect': 'update', 'type': '/type/text', 'value': macro }
}
infogami.write(q, comment='update book count')
