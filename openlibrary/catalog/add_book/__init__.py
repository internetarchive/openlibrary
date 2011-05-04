def load(rec):
    edition_pool = pool.build(rec)
    if not edition_pool:
        load_data(rec) # 'no books in pool, loading'

    rec['full_title'] = rec['title']
    if rec.get('subtitle'):
        rec['full_title'] += ' ' + rec['subtitle']
    e1 = build_marc(rec)

    if 'authors' in e1:
        for a in e1['authors']:
            date = None
            if 'date' in a:
                assert 'birth_date' not in a and 'death_date' not in a
                date = a['date']
            elif 'birth_date' in a or 'death_date' in a:
                date = a.get('birth_date', '') + '-' + a.get('death_date', '')
            a['db_name'] = ' '.join([a['name'], date]) if date else a['name']

    match = find_match(e1, edition_pool)

    if match: # 'match found:', match, rec['ia']
        add_source_records(match, ia)
    else: # 'no match found', rec['ia']
        load_data(rec)

    return {'note': 'loaded'}
