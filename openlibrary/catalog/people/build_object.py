from openlibrary.catalog.utils import flip_name, pick_first_date


def build_person_object(p, marc_alt):
    ab = [(k, v.strip(' /,;:')) for k, v in p if k in 'ab']

    has_b = any(k=='b' for k, v in p)

    orig_name = ' '.join(v if k == 'a' else v for k, v in ab)
    c = ' '.join(v for k, v in p if k == 'c')
    name = flip_name(orig_name)
    if name[0].isdigit():
        name = orig_name
    else:
        of_count = c.count('of ')
    #    if of_count == 1 and not has_b and 'of the ' not in c:
    #        if c.startswith('King')
    #
    #        if c.startswith('Queen'):
    #        name += ' ' + c[c.find('of '):]
    #
        if of_count == 1 and 'of the ' not in c and 'Emperor of ' not in c:
            name += ' ' + c[c.find('of '):]
        elif ' ' not in name and of_count > 1:
            name += ', ' + c
        elif c.endswith(' of') or c.endswith(' de') and any(k == 'a' and ', ' in v for k, v in p):
            name = ' '.join(v for k, v in ab)
            c += ' ' + name[:name.find(', ')]
            name = name[name.find(', ') + 2:] + ', ' + c

    person = {}
    d = [v for k, v in p if k =='d']
    if d:
        person = pick_first_date(d)
    person['name'] = name
    person['sort'] = orig_name

    if any(k=='b' for k, v in p):
        person['enumeration'] = ' '.join(v for k, v in p if k == 'b')

    if c:
        person['title'] = c
    person['marc'] = [p] + list(marc_alt)

    return person

def test_consort():
    line = (('a', u'Elizabeth'), ('c', u'Empress, consort of Franz Joseph, Emperor of Austria'))
    p = build_person_object(marc, [])
    p['name'] == u'Empress Elizabeth, consort of Franz Joseph, Emperor of Austria',

    line = (('a', u'Mary'), ('c', u'Queen, Consort of George V, King of Great Britain'), ('d', u'1867-1953'))
    p = build_person_object(marc, [])
    p['name'] == u'Queen Mary, Consort of George V, King of Great Britain'

def test_king_no_number():
    marc = (('a', u'Henry'), ('b', u'IV'), ('c', u'King of England'), ('d', u'1367-1413'))
    p = build_person_object(marc, [])
    assert p['name'] == u'Henry IV of England'

    marc = (('a', u'John'), ('c', u'King of England'), ('d', u'1167-1216'))
    p = build_person_object(marc, [])
    assert p['name'] == 'King John of England'

