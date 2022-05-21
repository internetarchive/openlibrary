#!/usr/bin/env python

import openlibrary.catalog.merge.merge_marc as marc
import openlibrary.catalog.merge.amazon as amazon
from openlibrary.catalog.utils.query import get_mc, withKey

from openlibrary.catalog.get_ia import get_from_archive
import openlibrary.catalog.marc.fast_parse as fast_parse


def try_amazon(key):
    thing = withKey(key)
    if 'isbn_10' not in thing:
        return None
    if 'authors' in thing:
        authors = []
        for a in thing['authors']:
            author_thing = withKey(a['key'])
            if 'name' in author_thing:
                authors.append(author_thing['name'])
    else:
        authors = []
    return amazon.build_amazon(thing, authors)


def get_record(key, mc):
    data = get_from_archive(mc)
    try:
        rec = fast_parse.read_edition(data)
    except (fast_parse.SoundRecording, IndexError, AssertionError):
        print(mc)
        print(key)
        return False
    try:
        return marc.build_marc(rec)
    except TypeError:
        print(rec)
        raise


def attempt_merge(a, m, threshold, debug=False):
    l1 = amazon.level1_merge(a, m)
    total = sum(i[2] for i in l1)
    if debug:
        print(total, l1)
    if total >= threshold:
        return True
    l2 = amazon.level2_merge(a, m)
    total = sum(i[2] for i in l2)
    if debug:
        print(total, l2)
    return total >= threshold


sample_amazon = {
    'publishers': ['New Riders Press'],
    'isbn': ['0321525655'],
    'number_of_pages': 240,
    'short_title': 'presentation zen simple i',
    'normalized_title': 'presentation zen simple ideas on presentation design and delivery voices that matter',
    'full_title': 'Presentation Zen Simple Ideas on Presentation Design and Delivery (Voices That Matter)',
    'titles': [
        'Presentation Zen Simple Ideas on Presentation Design and Delivery (Voices That Matter)',
        'presentation zen simple ideas on presentation design and delivery voices that matter',
        'Presentation Zen Simple Ideas on Presentation Design and Delivery',
        'presentation zen simple ideas on presentation design and delivery',
    ],
    'publish_date': '2007',
    'authors': ['Garr Reynolds'],
}
sample_marc = {
    'publishers': ['New Riders'],
    'isbn': ['9780321525659', '0321525655'],
    'lccn': ['2008297172'],
    'number_of_pages': 229,
    'short_title': 'presentation zen simple i',
    'normalized_title': 'presentation zen simple ideas on presentation design and delivery',
    'full_title': 'Presentation zen simple ideas on presentation design and delivery',
    'titles': [
        'Presentation zen simple ideas on presentation design and delivery',
        'presentation zen simple ideas on presentation design and delivery',
    ],
    'publish_date': '2008',
    'publish_country': 'cau',
    'authors': [{'db_name': 'Reynolds, Garr.', 'name': 'Reynolds, Garr.'}],
}


def amazon_and_marc(key1, key2):
    if all(k in ('/b/OL9621221M', '/b/OL20749803M') for k in (key1, key2)):
        return sample_amazon, sample_marc
    mc1 = get_mc(key1)
    mc2 = get_mc(key2)
    if mc1.startswith('amazon:'):
        assert not mc2.startswith('amazon:')
        rec_amazon = try_amazon(key1)
        rec_marc = get_record(key2, mc2)
    else:
        assert mc2.startswith('amazon:')
        rec_amazon = try_amazon(key2)
        rec_marc = get_record(key1, mc1)
    return rec_amazon, rec_marc


def marc_and_marc(key1, key2):
    mc1 = get_mc(key1)
    rec1 = get_record(key1, mc1)
    mc2 = get_mc(key2)
    rec2 = get_record(key2, mc2)
    return rec1, rec2


if __name__ == '__main__':
    key1 = '/b/OL9621221M'  # amazon
    key2 = '/b/OL20749803M'
    rec_amazon, rec_marc = amazon_and_marc(key1, key2)
    threshold = 875
    print(attempt_merge(rec_amazon, rec_marc, threshold, debug=True))
