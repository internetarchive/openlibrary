from solr_fields import excluded_fields
from facet_hash import facet_token
from traceback import print_exc
import re
import pdb

mutatelist = []
def mutate(func):
    mutatelist.append(func)
    return func

# in some books, 'identifier' is stored as 'key'
@mutate
def mutate_identifier(book):
    if 'key' in book:
        book['identifier'] = book['key']
        del book['key']

# remove the 'id' field which is an internal infobase thing, distinct
# from 'identifier' which is used by solr
@mutate
def mutate_id(book):
    if 'id' in book:
        del book['id']

# remove the book description before inserting catchall fields.  We
# don't want to index the descriptions because they match too many
# queries.  Think of them as keyword spam.
@mutate
def rm_description(book):
    if 'description' in book:
        del book['description']

# insert catchall fields, before running further mutates since
# those are going to insert additional fields that we don't(?)
# want to toss into the catchall.
@mutate
def mutate_catchall(book):
    kset = set(book.keys()) - excluded_fields
    kset.remove('identifier')
    text = []
    seen = set()
    def bt(b):
        if type(b) in (str, unicode):
            bl = b.lower()
            if bl not in seen:
                text.append(b)
                seen.add(bl)
    for k in kset:
        b = book[k]
        if type(b) == list:
            map(bt, b)
        else:
            bt(b)
    if text:
        # remove duplicates
        text = sorted(set(text))
        book['text'] = text

@mutate
def mutate_title(book):
    tpl = int(book.get('title_prefix_len', 0))
    book['titleSorter'] = book.get('title','')[tpl:]
    
@mutate
def mutate_date(book):
    pd = book.get('publish_date')
    if not pd: return
    pyr = re.search(r'[0-9]{4}', pd)
    if not pyr: return
    py = pyr.group(0)

    book['publication_year'] = py
    book['facet_year'] = facetize_year(py)
    
# String -> String
def facetize_year(yyyy):
    """Convert 4-digit numeric year to the facet string for its
    date range, usually a 20 year period.  The facet strings
    are 2000, 1980, 1960, 1940, 1920, pre1920, and unknown
    >>> print facetize_year(2007)
    2000
    >>> print facetize_year(2000)
    2000
    >>> print facetize_year(1997)
    1980
    >>> print facetize_year(1923)
    1920
    >>> print facetize_year(1920)
    1920
    >>> print facetize_year(1919)
    pre1920
    >>> print facetize_year(5864)  # hebrew calendar year
    unknown
    """
    y = int(yyyy)
    if 1920 <= y <= 2010:
        return '%d' % (y - (y % 20))
    elif y < 1920:
        return 'pre1920'
    else:
        return 'unknown'

@mutate
def mutate_isbn(book):
    isbns = book.get('isbn_10', []) + book.get('isbn_13', [])
    # strip all non-digits from the isbn's, since they are sometimes
    # entered with hyphens and the like.  Non-digits also have to
    # be stripped from the search queries.
    def clean(isbn):
        return ''.join(filter(unicode.isdigit, unicode(isbn)))
    isbns = filter(bool, map(clean, isbns))
    if isbns:
        book['isbn'] = ' '.join(isbns)

@mutate
def mutate_scan_status(book):
    # we now apparently use scan_on_demand=true to denote a scannable
    # book.  Convert this to the old 'scan_status' field, which will
    # then get picked up by mutate_fulltext, below.
    if bool(book.get('scan_on_demand')):
        del book['scan_on_demand']
        book['scan_status'] = 'NOT_SCANNED'

@mutate
def mutate_fulltext(book):
    # book['ocaid'] is either absent, none, the empty string, or
    # some other string.  We want to facet it as '1' if it's a
    # nonempty string and as '0' in each of the other cases.
    ft = str(int(bool(book.get('ocaid')))) # '1' or '0'
    assert (ft in '10'), 'invalid fulltext...'
    if ft == '0' and book.get('scan_status') == 'NOT_SCANNED':
        ft = '5'
    book['has_fulltext'] = ft

@mutate
def mutate_subjects(book):
    def get_list(field):
        # get field from book, and return it in list form, i.e.
        # wrap it into a list if it is not already a list.
        a = book.get(field, [])
        return (a if type(a) == list else [a])
        
    all_subjects = get_list('subject') + get_list('subjects')
    if all_subjects:
        book['subjects'] = sorted(set(all_subjects))
    if 'subject' in book:
        del book['subject']

@mutate
def mutate_facet_tokens(book):
    facet_fields = [  ["authors"]
                    , ["publishers"]
                    , ["subjects"]
                    , ["subject", "subjects"]
                    , ["source"]
                    , ["language"]
                    , ["languages"]
                    , ["language_code"]
                    , ["has_fulltext"]
                    , ["facet_year"]
                   ]
    all_tokens = []
    for ff in facet_fields:
        fieldname = ff[0]
        label = fieldname if len(ff) == 1 else ff[1]
#        if 'sub' in label: pdb.set_trace()
        vs = book.get(fieldname)
        if type(vs) != list:
            vs = [vs]
        all_tokens.extend(facet_token(label, v) for v in vs if v)

    all_tokens = sorted(set(all_tokens))

    if all_tokens:
        book['facet_tokens'] = ' '.join(all_tokens)

def run_mutations(b):
    for h in mutatelist: h(b)
    return b
