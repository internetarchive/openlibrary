#!/usr/bin/python

from catalog.marc.parse import parser
from catalog.merge.names import flip_marc_name
from time import time
import codecs, shelve, re, sys
import catalog.marc.MARC21
import psycopg2

skip_keys = set(['key', 'comment', 'type', 'machine_comment', 'create', 'authors'])

conn = psycopg2.connect("dbname='infobase_data' user='edward' password=''");
cur = conn.cursor()

def sql_get_val (sql):
    cur.execute(sql)
    rows = cur.fetchall()
    return rows[0][0]

def sql_do (sql):
    cur.execute(sql)

thing_id = sql_get_val("select max(id) from thing")
version_id = sql_get_val("select max(id) from version")

edition_type = str(sql_get_val("select id from thing where key='/type/edition'"))
author_type = str(sql_get_val("select id from thing where key='/type/author'"))
author_key = {}

re_escape = re.compile(r'[\n\r\t\0\\]')
trans = { '\n': '\\n', '\r': '\\r', '\t': '\\t', '\\': '\\\\', '\0': '', }

def esc_group(m):
    return trans[m.group(0)]

def esc(str): return re_escape.sub(esc_group, str)

type_map = {
    'description': 'text',
    'notes': 'text',
    'number_of_pages': 'int',
    'url': 'uri',
}

type_map2 = { 'text': '3', 'int': '6', 'uri': '4' }

pharos = "/1/pharos/"
files = [ "marc_records_scriblio_net/part%02d.dat" % x for x in range(1,30) ]
files.reverse()
edition_num = 0
t0 = time()
total = 7022999
books = []
progress = open('progress', 'w')

author_num = 0

author_cache = {}

def import_author(author):
    global author_num
    name = unicode(author["db_name"].replace("\0", ""))
    if name in author_cache:
        return { 'key': author_cache[name] }
    else:
        author_num+=1
        key = '/a/OL%dA' % author_num
        a = {
            'create': 'unless_exists',
            'comment': 'initial import',
            'type': { 'key': '/type/author' },
            'key': '/a/OL%dA' % author_num,
            'name': author['name']
        }
        for f in 'title', 'personal_name', 'enumeration', 'birth_date', 'death_date':
            if f in author:
                a[f] = author[f]
        author_cache[name] = key
        return a

def write_edition(edition_data, edition_num):
    global books
    book_key = '/b/OL%dM' % edition_num
    book = {
        'create': 'unless_exists',
        'comment': 'initial import',
        'machine_comment': edition_data['source_record_loc'],
        'type': { 'key': '/type/edition' },
        'key': book_key
    }
    for k, v in edition_data.iteritems():
        if k == 'edition' and v == '':
            continue
        if k == 'source_record_loc' or k.startswith('language'):
            continue
        if k == 'authors':
            book[k] = [import_author(v[0])]
            continue
        if k in type_map:
            t = '/type/' + type_map[k]
            if isinstance(v, list):
                book[k] = [{'type': t, 'value': i} for i in v]
            else:
                book[k] = {'type': t, 'value': v}
        else:
            book[k] = v
    books.append(book)
    if edition_num % 1000 == 0:
        t1 = time() - t0
        remaining = total - edition_num
        print "%9d books loaded. running: %.1f hours. %.1f rec/sec. %.1f hours left: %s %s" % (edition_num, t1/3600, edition_num/t1, ((t1/edition_num) * remaining) / 3600, edition_data['source_record_loc'], `edition_data['title']`)
        progress.write(`edition_num, int(t1), edition_data['source_record_loc'], edition_data['title']` + "\n")
        progress.flush()
    if edition_num % 10000 == 0:
        bulk_load(books)
        books = []

bad_data_file = open('bad_data', 'w')
def bad_data(record_source_loc):
    bad_data_file.write(record_source_loc + "\n")

def write_datum(datum, thing_id, k, v, num):
    if isinstance(v, dict):
        data_type = type_map2[v['type'][6:]]
        v = v['value']
    else:
        data_type = '2' # string
    datum.write("\t".join((str(thing_id), '1', '\N', k, esc(unicode(v)), data_type, num)) + "\n")

def bulk_load(books):
    global thing_id, version_id
    thing = codecs.open("/var/tmp/thing", "w", "utf-8")
    version = codecs.open("/var/tmp/version", "w", "utf-8")
    datum = codecs.open("/var/tmp/datum", "w", "utf-8")

    for edition in books:
        thing_id += 1
        version_id += 1
        thing.write("\t".join((str(thing_id), '1', edition['key'], '1', '\N', '\N', '\N')) + "\n");
        version.write("\t".join((str(version_id), str(thing_id), '1', '\N', '\N', edition['comment'], edition['machine_comment'], '\N')) + "\n");
        datum.write("\t".join((str(thing_id), '1', '\N', 'type', edition_type, '0', '\N')) + "\n")

        for k, v in edition.iteritems():
            if k in skip_keys:
                continue
            if isinstance(v, list):
                for a, b in enumerate(v):
                    write_datum(datum, thing_id, k, b, str(a))
            else:
                write_datum(datum, thing_id, k, v, '\N')

        if 'authors' in edition:
            edition_thing_id = thing_id
            num = 0
            for author in edition['authors']:
                if len(author) == 1:
                    datum.write("\t".join((str(edition_thing_id), '1', '\N', 'authors', str(author_key[author['key']]), '0', str(num))) + "\n")
                    num+=1
                    continue
                thing_id += 1
                author_key[author['key']] = thing_id
                version_id += 1
                datum.write("\t".join((str(edition_thing_id), '1', '\N', 'authors', str(thing_id), '0', str(num))) + "\n")
                num += 1
                thing.write("\t".join((str(thing_id), '1', author['key'], '1', '\N', '\N', '\N')) + "\n");
                version.write("\t".join((str(version_id), str(thing_id), '1', '\N', '\N', author['comment'], '\N', '\N')) + "\n");
                datum.write("\t".join((str(thing_id), '1', '\N', 'type', author_type, '0', '\N')) + "\n")
                for k, v in author.iteritems():
                    if k in skip_keys:
                        continue
                    datum.write("\t".join((str(thing_id), '1', '\N', k, esc(unicode(v)), '2', '\N')) + "\n")


    thing.close()
    version.close()
    datum.close()
    print "loading batch of editions into database"
    sql_do("copy thing from '/var/tmp/thing'")
    sql_do("copy version from '/var/tmp/version'")
    sql_do("copy datum from '/var/tmp/datum'")
    conn.commit()

    print "batch of editions loaded"

edition_num = 0
for file_locator in files:
    input = open(pharos + file_locator)
    try:
        for edition_data in parser(file_locator, input, bad_data):
            edition_num+=1
            write_edition(edition_data, edition_num)
    except catalog.marc.MARC21.MARC21Exn:
        pass
    input.close()

bad_data_file.close()
progress.close()
t1 = time() - t0
print "total run time: %.1f" % (t1/3600)
