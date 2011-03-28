# -*- coding: utf-8 -*-
from find_works import top_rev_wt, has_dot, freq_dict_top, find_works, get_books, find_works2, build_work_title_map, find_works3, find_work_sort
from openlibrary.catalog.merge.normalize import normalize

def test_has_dot():
    assert has_dot('Magic.')
    assert not has_dot('Magic')
    assert not has_dot('Magic etc.')

def test_top_rev_wt():
    input_data = {
        'aaa': 'test data',
        'aaaa': 'more test data',
        'bbbb': 'test date',
        'cc': 'some more test data',
    }
    assert top_rev_wt(input_data) == 'bbbb'

def test_freq_dict_top():
    assert freq_dict_top({'a': 0}) == 'a'
    assert freq_dict_top({'a': 3, 'b': 6, 'c': 4}) == 'b'

def test_find_works():
    works = list(find_works([]))
    assert works == []

    books = [{'title': 'Magic', 'key': '/books/OL1M'}]
    book_iter = get_books('', books, do_get_mc=False)

    books2 = list(book_iter)
    assert books2 == [{'key': '/books/OL1M', 'norm_title': 'magic', 'title': 'Magic'}]

    var = find_works2(books2)
    assert var['equiv'] == {}
    assert var['norm_titles'] == {'magic': 1}
    assert var['books_by_key'] == {'/books/OL1M': books2[0]}
    assert var['books'] == books2
    assert var['rev_wt'] == {}

    assert build_work_title_map({}, {'magic': 1}) == {}
    assert build_work_title_map({}, {'magic': 2, 'test': 0}) == {}

    works = list(find_works(books2, do_get_mc=False))
    expect = [
    { 'title': 'Magic',
        'editions': [{
        'key': '/books/OL1M',
        'norm_title': 'magic',
        'title': 'Magic'}],
    }]
    assert works == expect


    books = [
        {'title': 'Magic', 'key': '/books/OL1M'},
        {'title': 'Magic', 'key': '/books/OL2M'},
    ]
    book_iter = get_books('', books, do_get_mc=False)
    books2 = list(book_iter)

    var = find_works2(books2)
    assert var['equiv'] == {}
    assert var['norm_titles'] == {'magic': 2}
    assert var['books_by_key'] == {'/books/OL1M': books2[0], '/books/OL2M': books2[1]}
    assert var['books'] == books2
    assert var['rev_wt'] == {}

    works = list(find_works(books2, do_get_mc=False))
    expect = [
    { 'title': 'Magic',
        'editions': [
            { 'key': '/books/OL1M', 'norm_title': 'magic', 'title': 'Magic'},
            { 'key': '/books/OL2M', 'norm_title': 'magic', 'title': 'Magic'},
        ],
    }]
    assert works == expect

    magico = u'm\xe1gico'

    assert normalize(magico) == magico

    books = [
        {'title': magico, 'work_title': ['magic'], 'key': '/books/OL1M'},
        {'title': 'magic', 'key': '/books/OL2M'},
        {'title': magico, 'work_title': ['magic'], 'key': '/books/OL3M'},
        {'title': 'magic', 'key': '/books/OL4M'},
    ]
    expect_keys = sorted(e['key'] for e in books)
    book_iter = get_books('', books, do_get_mc=False)
    books2 = list(book_iter)

    expect = [
        {'key': '/books/OL1M', 'norm_title': magico, 'work_title': 'magic', 'norm_wt': 'magic', 'title': magico},
        {'key': '/books/OL2M', 'norm_title': 'magic', 'title': 'magic'},
        {'key': '/books/OL3M', 'norm_title': magico, 'work_title': 'magic', 'norm_wt': 'magic', 'title': magico},
        {'key': '/books/OL4M', 'norm_title': 'magic', 'title': 'magic'},
    ]

    assert len(books2) == 4
    for i in range(4):
        assert books2[i] == expect[i]

    var = find_works2(books2)
    assert var['equiv'] == {(magico, 'magic'): 2}
    assert var['norm_titles'] == {magico: 2, 'magic': 2}
    assert len(var['books_by_key']) == 4
    bk = var['books_by_key']
    assert bk['/books/OL1M'] == books2[0]
    assert bk['/books/OL2M'] == books2[1]
    assert bk['/books/OL3M'] == books2[2]
    assert bk['/books/OL4M'] == books2[3]
    assert var['books'] == books2
    assert var['rev_wt'] == {'magic': {'magic': 2}}

    title_map = build_work_title_map(var['equiv'], var['norm_titles'])

    assert title_map == {magico: 'magic'}

    find_works3(var)
    assert var['works'] == {'magic': {'magic': expect_keys}}
    assert var['work_titles'] == {'magic': ['/books/OL1M', '/books/OL3M']}

    sorted_works = find_work_sort(var)
    assert sorted_works == [(6, 'magic', {'magic': expect_keys})]

    works = list(find_works(books2, do_get_mc=False))
    expect = [{
        'title': u'Magic',
        'editions': [
            {'key': '/books/OL2M', 'norm_title': 'magic', 'title': 'magic'},
            {'key': '/books/OL1M', 'norm_title': u'mágico', 'norm_wt': 'magic', 'title': u'Mágico'},
        ], 
    }]

    work_count = len(works)
    assert work_count == 1
    editions = works[0]['editions']
    edition_count = len(works[0]['editions'])
    edition_keys = sorted(e['key'] for e in editions) 
    assert edition_keys == expect_keys
    assert edition_count == 4
    del works[0]['editions']
    assert works[0] == {'title': 'magic'}
    #assert works == expect


