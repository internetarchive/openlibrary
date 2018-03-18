import csv, httplib, sys, codecs, re
from openlibrary.api import OpenLibrary
from pprint import pprint, pformat

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

h1 = httplib.HTTPConnection('www.archive.org')
h1.connect()

ol = OpenLibrary('http://openlibrary.org/')
#ol.login('EdwardBot', 'As1Wae9b')

input_file = '/home/edward/Documents/smashwords_ia_20110325.csv'
input_file = '/home/edward/Documents/smashwords_ia_20110325-extended-20110406.csv'

#headings = ['Distributor', 'Author Name', 'Author Bio', 'Publisher', 'SWID',
#    'Book Title', 'Price', 'Short Book Description', 'Long Book Description',
#    'ISBN', 'BISAC I', 'BISAC II', 'Where to buy']

# ['Distributor', 'Author Name', 'Author Bio', 'Publisher', 'SWID',
# 'Book Title', 'Pub. Date @ Smashwords', 'Price', 'Short Book Description',
# 'Long Book Description', 'ISBN', 'BISAC I', 'BISAC II', 'Word Count (Approx.)',
# 'Where to buy']

authors = {}
titles = set()
isbn = set()

name_map = {
    'JA Konrath': 'J. A. Konrath'
}

done = set(['978-1-4523-2945-1', '978-1-4523-0368-0', '978-1-4523-4686-1',
            '978-0-981-94368-8', '978-0-987-05532-3', '978-0-987-05533-0',
            '978-0-987-05533-0', '978-1-4523-3743-2', '978-1-4523-4108-8',
            '978-1-4523-1429-7', '978-1-4523-9020-8', '978-1-4523-2207-0',
            '978-1-4523-9091-8', '978-1-4523-8731-4', '978-1-4523-7639-4',
            'SW00000046140', '978-1-4523-4426-3', '978-1-4523-0687-2',
            '978-1-4523-0686-5', '978-1-4523-0684-1', '978-1-4523-0683-4',
            '978-1-4524-0245-1', '978-1-4524-0243-7', '978-1-102-46655-0',
            '978-1-4523-0372-7', '978-1-4523-0321-5', '978-1-4523-6775-0',
            '978-1-4580-7969-5', '978-1-4523-8020-9', '978-1-4581-8282-1',
            '978-1-4523-5564-1', 'SW00000047707', '978-1-4523-5204-6',
            '978-1-4523-1740-3', '978-1-4523-5559-7', '978-1-4523-5601-3',
            '978-1-4581-3793-7', '978-1-4523-8141-1', '978-1-4523-5065-3',
            '978-1-4580-0894-7', '978-1-4580-8419-4', '978-1-4523-2360-2',
            '978-1-4523-1861-5', '978-1-4523-9376-6', '978-1-4581-3742-5',
            '978-1-4523-6574-9', '978-1-4523-2484-5', '978-1-4523-2607-8',
            '978-1-4523-7547-2', '978-1-4523-5034-9', '978-0-976-22351-1',
            '978-1-102-46644-4', '978-1-4523-2826-3', '978-1-102-46945-2',
            '978-1-4523-4192-7', '978-1-4523-0388-8', '978-1-4523-0385-7',
            '978-1-4523-0382-6', '978-1-4523-0376-5', '978-1-4523-0375-8',
            '978-1-4523-0367-3', '978-1-4523-0362-8', '978-1-4523-0359-8',
            '978-1-4523-0353-6', '978-1-4523-0346-8', '978-1-4523-0341-3',
            '978-1-4523-0330-7', '978-1-4523-0317-8', '978-1-4523-0309-3',
            '978-1-4523-0286-7', '978-0-986-59422-9', '978-1-4523-5506-1',
            '978-1-4523-7693-6', '978-1-4523-8473-3', '978-1-4523-2417-3',
            '978-1-4523-5642-6', '978-1-4523-2123-3', '978-1-4523-4620-5',
            '978-1-4523-6227-4', '978-1-4523-3639-8', '978-1-4523-7777-3',
            '978-1-4523-8301-9', '978-1-4523-1636-9', '978-1-4523-7388-1',
            '978-1-4523-7016-3', '978-1-4523-8655-3', '978-1-4523-8749-9',
            '978-1-4523-9632-3'])

print len(done)

re_pub_date = re.compile('^(20\d\d)/(\d\d)/(\d\d) \d\d:\d\d:\d\d$')

headings = None
check_ia = False
for row in csv.reader(open(input_file)):
    if not headings:
        headings = row
        print row
        continue
    book = dict(zip(headings, [s.decode('utf-8') for s in row]))
    if book['Distributor'] != 'Smashwords':
        print book['Distributor']
    assert book['Distributor'] == 'Smashwords'
    assert book['Publisher'] == ''
    assert book['SWID'].isdigit()
    author_name = book['Author Name']
    if author_name in name_map:
        author_name = name_map[author_name]
    author_bio = book['Author Bio']
    isbn = book['ISBN']

    #if isbn:
    #    existing = ol.query({'type':'/type/edition', 'isbn_13': isbn})
    #print existing
    #continue

    title = book['Book Title']
    #print(repr(isbn, title))
    assert isbn == '' or isbn.replace('-', '').isdigit()
    assert title not in titles
    titles.add(title)
    if book['Author Name'] not in authors:
        authors[author_name] = {
            'name': book['Author Name'],
            'bio': author_bio,
            'editions': []
        }
    else:
        assert authors[author_name]['bio'] == author_bio
    author = authors[author_name]

    ia = isbn if isbn else 'SW000000' + book['SWID']

    if ia in done:
        continue

    pprint(book)

    if check_ia:
        h1.request('GET', 'http://www.archive.org/download/' + ia)
        res = h1.getresponse()
        print res.getheader('location')
        res.read()

    m = re_pub_date.match(book['Pub. Date @ Smashwords'])
    date = '-'.join(m.groups())

    edition = { 'title': title, 'ia': ia, 'publish_date': date, }
    if isbn:
        edition['isbn_13'] = isbn.replace('-', '')
    if book['Long Book Description']:
        edition['description'] = book['Long Book Description']
    elif book['Short Book Description']:
        edition['description'] = book['Short Book Description']
    #print edition
    author['editions'].append(edition)

#sys.exit(0)

print len(authors)

authors_done = set([u'Zoe Winters', u'Derek Ciccone', u'Shayne Parkinson', u'Joanna Penn'])
if False:
    for k in [u'Zoe Winters', u'Derek Ciccone', u'Shayne Parkinson', u'Joanna Penn']:
        v = authors[k]
        akey = ol.new({
            'type': '/type/author',
            'name': k,
            'bio': v['bio'],
        })
        print
        print akey, k
        for e in v['editions']:
            wkey = ol.new({
                'type': '/type/work',
                'title': e['title'],
                'authors': [{'author': {'key': akey}}],
                'description': e['description'],
                'subjects': ['Lending library'],
            })
            print wkey, e['title']
            edition = {
                'type': '/type/edition',
                'title': e['title'],
                'authors': [{'key': akey}],
                'works': [{'key': wkey}],
                'ocaid': e['ia'],
                'publishers': ['Smashwords'],
            }
            if 'isbn' in e:
                edition['isbn'] = e['isbn']
            ekey = ol.new(edition)
            print ekey, e['title']
        continue

update = {}
for k, v in authors.items():
    if not v['editions']:
        continue
    authors = ol.query({'type': '/type/author', 'name': k})
    assert authors
    if not authors:
        assert k in authors_done
        continue
        author_done.append(k)
        print {'name': k, 'bio': v['bio'] }
        for e in v['editions']:
            pprint({
                'title': e['title'],
                'authors': {'author': {'key': 'xxx'}},
                'description': e['description'],
            })
        print
        continue
        print('bio:', repr(v['bio']))
        print('editions')
        pprint(v['editions'])
        print
    if authors:
        akey = authors[0]
        #print k, map(str, authors)
        q = {
            'type': '/type/work',
            'authors': {'author': {'key': akey} },
            'title': None,
        }
        works = list(ol.query(q))
        work_titles = [(w['title'].lower(), w) for w in works]
        for e in v['editions']:
            q = {'type': '/type/edition', 'ocaid': e['ia']}
            existing = list(ol.query(q))
            if existing:
                print existing
                print 'skip existing:', str(existing[0]), e['ia']
                continue
            print e
            assert not any(e['title'].lower().startswith(t) for t, w in work_titles)
            if k not in update:
                update[k] = dict((a, b) for a, b in v.items() if a != 'editions')
                update[k]['key'] = str(akey)
                update[k]['editions'] = []
            update[k]['editions'].append(e)
            continue
            for t, w in work_titles:
                if not e['title'].lower().startswith(t):
                    continue
                if k not in update:
                    update[k] = dict((a, b) for a, b in v.items() if a != 'editions')
                    update[k]['key'] = str(akey)
                    update[k]['editions'] = []
                e['work'] = w['key']
                update[k]['editions'].append(e)
                q = {'type': '/type/edition', 'works': w['key'], 'ocaid': None}
                assert all(not e['ocaid'] for e in ol.query(q))
                print dict((a,b) for a, b in v.items() if a != 'editions')
                print 'new:', e
                print 'work:', w
                print
                break

h1.close()

pprint(update.values(), stream=open('update2', 'w'))
