from openlibrary.catalog.merge.merge import (
    full_title,
    build_titles,
    compare_title,
)

""" These tests seem to be duplicates of those in test_amazon.py,
    which in turn are duplicates of methods that are actually used
    by Open Library in openlibrary.catalog.merge.merge_marc
    Investigate and clean up!
    """


def test_full_title():
    assert full_title({'title': "Hamlet"}) == "Hamlet"
    edition = {
        'title': 'Flatland',
        'subtitle': 'A Romance of Many Dimensions',
    }
    assert full_title(edition) == "Flatland A Romance of Many Dimensions"


def test_merge_titles():
    marc = {
        'title_with_subtitles': (
            'Spytime : the undoing of James Jesus Angleton : a novel'
        ),
        'title': 'Spytime',
        'full_title': 'Spytime : the undoing of James Jesus Angleton : a novel',
    }
    amazon = {
        'subtitle': 'The Undoing oF James Jesus Angleton',
        'title': 'Spytime',
    }

    amazon = build_titles(full_title(amazon))
    marc = build_titles(marc['title_with_subtitles'])
    assert amazon['short_title'] == marc['short_title']
    assert compare_title(amazon, marc) == (
        'full-title',
        'contained within other title',
        350,
    )


def test_merge_titles2():
    amazon = {'title': 'Sea Birds Britain Ireland'}
    marc = {
        'title_with_subtitles': 'seabirds of Britain and Ireland',
        'title': 'seabirds of Britain and Ireland',
        'full_title': 'The seabirds of Britain and Ireland',
    }
    amazon = build_titles(full_title(amazon))
    marc = build_titles(marc['title_with_subtitles'])
    assert compare_title(amazon, marc) == ('full-title', 'exact match', 600)
