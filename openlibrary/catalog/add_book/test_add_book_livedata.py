from __future__ import print_function

import pytest
from collections import defaultdict

from openlibrary.catalog.add_book import load
from openlibrary.catalog.add_book.test_load_book import add_languages
from openlibrary.catalog.marc.marc_binary import MarcBinary, BadLength, BadMARC
from openlibrary.catalog.marc.parse import read_edition

from six.moves.urllib.request import urlopen


#@pytest.mark.parametrize('ocaid', dq)
def test_don_quixote(mock_site, add_languages):
    """
    All of these items are by 'Miguel de Cervantes Saavedra',
    only one Author should be created. Some items have bad
    MARC length, others are missing binary MARC altogether
    and raise BadMARC exceptions.
    """
    pytest.skip("This test make live requests to archive.org")

    dq = [u'lifeexploitsofin01cerv', u'cu31924096224518',
        u'elingeniosedcrit04cerv', u'ingeniousgentlem01cervuoft',
        u'historyofingenio01cerv', u'lifeexploitsofin02cerviala',
        u'elingeniosohidal03cervuoft', u'nybc209000', u'elingeniosohidal11cerv',
        u'elingeniosohidal01cervuoft', u'elingeniosoh01cerv',
        u'donquixotedelama00cerviala', u'1896elingeniosohid02cerv',
        u'ingeniousgentlem04cervuoft', u'cu31924027656978', u'histoiredeladmir01cerv',
        u'donquijotedelama04cerv', u'cu31924027657075', u'donquixotedelama03cervuoft',
        u'aventurasdedonqu00cerv', u'p1elingeniosohid03cerv',
        u'geshikhefundonik01cervuoft', u'historyofvalorou02cerviala',
        u'ingeniousgentlem01cerv', u'donquixotedelama01cervuoft',
        u'ingeniousgentlem0195cerv', u'firstpartofdelig00cervuoft',
        u'p4elingeniosohid02cerv', u'donquijote00cervuoft', u'cu31924008863924',
        u'c2elingeniosohid02cerv', u'historyofvalorou03cerviala',
        u'historyofingenio01cerviala', u'historyadventure00cerv',
        u'elingeniosohidal00cerv', u'lifeexploitsofin01cervuoft',
        u'p2elingeniosohid05cerv', u'nybc203136', u'elingeniosohidal00cervuoft',
        u'donquixotedelama02cervuoft', u'lingnieuxcheva00cerv',
        u'ingeniousgentlem03cerv', u'vidayhechosdeli00siscgoog',
        u'lifeandexploits01jarvgoog', u'elingeniosohida00puiggoog',
        u'elingeniosohida00navagoog', u'donquichottedel02florgoog',
        u'historydonquixo00cogoog', u'vidayhechosdeli01siscgoog',
        u'elingeniosohida28saavgoog', u'historyvalorous00brangoog',
        u'elingeniosohida01goog', u'historyandadven00unkngoog',
        u'historyvalorous01goog', u'ingeniousgentle11saavgoog',
        u'elingeniosohida10saavgoog', u'adventuresdonqu00jarvgoog',
        u'historydonquixo04saavgoog', u'lingnieuxcheval00rouxgoog',
        u'elingeniosohida19saavgoog', u'historyingeniou00lalagoog',
        u'elingeniosohida00ormsgoog', u'historyandadven01smolgoog',
        u'elingeniosohida27saavgoog', u'elingeniosohida21saavgoog',
        u'historyingeniou00mottgoog', u'historyingeniou03unkngoog',
        u'lifeandexploits00jarvgoog', u'ingeniousgentle00conggoog',
        u'elingeniosohida00quixgoog', u'elingeniosohida01saavgoog',
        u'donquixotedelam02saavgoog', u'adventuresdonqu00gilbgoog',
        u'historyingeniou02saavgoog', u'donquixotedelam03saavgoog',
        u'elingeniosohida00ochogoog', u'historyingeniou08mottgoog',
        u'lifeandexploits01saavgoog', u'firstpartdeligh00shelgoog',
        u'elingeniosohida00castgoog', u'elingeniosohida01castgoog',
        u'adventofdonquixo00cerv', u'portablecervante00cerv',
        u'firstpartofdelig14cerv', u'donquixotemanofl00cerv',
        u'firstpartofdelig00cerv']

    bad_length = []
    bad_marc = []

    edition_status_counts = defaultdict(int)
    work_status_counts = defaultdict(int)
    author_status_counts = defaultdict(int)

    for ocaid in dq:
        marc_url = 'https://archive.org/download/%s/%s_meta.mrc' % (ocaid, ocaid)
        try:
            data = urlopen(marc_url).read()
            marc = MarcBinary(data)
        except BadLength:
            bad_length.append(ocaid)
            continue
        except BadMARC:
            bad_marc.append(ocaid)
            continue
        except Exception as e:
            print('Problem with %s: %s' % (ocaid, e))
            continue

        rec = read_edition(marc)
        rec['source_records'] = ['ia:' + ocaid]
        reply = load(rec)

        q = {
            'type': '/type/work',
            'authors.author': '/authors/OL1A',
        }
        work_keys = list(mock_site.things(q))
        author_keys = list(mock_site.things({'type': '/type/author'}))
        print("\nReply for %s: %s" % (ocaid, reply))
        print("Work keys: %s" % work_keys)
        assert author_keys == ['/authors/OL1A']
        assert reply['success'] is True

        # Increment status counters
        edition_status_counts[reply['edition']['status']] += 1
        work_status_counts[reply['work']['status']] += 1
        if (reply['work']['status'] != 'matched') and (reply['edition']['status'] != 'modified'):
            # No author key in response if work is 'matched'
            # No author key in response if edition is 'modified'
            author_status_counts[reply['authors'][0]['status']] += 1

    print("BAD MARC LENGTH items: %s" % bad_length)
    print("BAD MARC items: %s" % bad_marc)
    print("Edition status counts: %s" % edition_status_counts)
    print("Work status counts: %s" % work_status_counts)
    print("Author status counts: %s" % author_status_counts)
