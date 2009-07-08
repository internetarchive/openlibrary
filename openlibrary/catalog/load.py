type_map = {
    'description': 'text',
    'notes': 'text',
    'number_of_pages': 'int',
    'url': 'uri',
}

def get_author_num(web):
    # find largest author key
    rows = web.query("select key from thing where site_id=1 and key LIKE '/a/OL%%A' order by id desc limit 10")
    return max(int(web.numify(i.key)) for i in rows)

def get_edition_num(web):
    # find largest edition key
    rows = web.query("select key from thing where site_id=1 and key LIKE '/b/OL%%M' order by id desc limit 10")
    return max(int(web.numify(i.key)) for i in rows)

def add_keys(web, edition):
    # add author and edition keys to a new edition
    if 'authors' in edition:
        for a in edition['authors']:
            a.setdefault('key', '/a/OL%dA' % (get_author_num(web) + 1))
    edition['key'] = '/b/OL%dM' % (get_edition_num(web) + 1)

def build_query(loc, rec):
    if 'title' not in rec:
        print 'missing title:', loc
        return
    if 'edition_name' in rec:
        assert rec['edition_name']
    assert 'source_record_loc' not in rec

    book = {
        'create': 'unless_exists',
        'type': { 'key': '/type/edition'},
    }

    east = east_in_by_statement(rec)
    if east:
        print rec

    for k, v in rec.iteritems():
        if k == 'authors':
            book[k] = [import_author(v[0], eastern=east)]
            continue
        if k in type_map:
            t = '/type/' + type_map[k]
            if isinstance(v, list):
                book[k] = [{'type': t, 'value': i} for i in v]
            else:
                book[k] = {'type': t, 'value': v}
        else:
            book[k] = v

    if 'title' not in book:
        pprint(rec)
        pprint(book)
    assert 'title' in book
    if 'publish_country' in book:
        assert book['publish_country'] not in ('   ', '|||')
    if 'publish_date' in book:
        assert book['publish_date'] != '||||'
    if 'languages' in book:
        lang_key = book['languages'][0]['key']
        if lang_key in ('/l/   ', '/l/|||'):
            del book['languages']
        elif not site.things({'key': lang_key, 'type': '/type/language'}):
            print lang_key, "not found for", loc
            del book['languages']
    return book

