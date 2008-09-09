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
