import json
import sys
from typing import Hashable, Iterable, Mapping, Optional

import web

from openlibrary.plugins.openlibrary.processors import urlsafe
from openlibrary.core import helpers as h
from openlibrary.core import ia

from infogami.utils.delegate import register_exception


def split_key(bib_key: str) -> tuple[Optional[str], Optional[str]]:
    """
    >>> split_key('1234567890')
    ('isbn_', '1234567890')
    >>> split_key('ISBN:1234567890')
    ('isbn_', '1234567890')
    >>> split_key('ISBN1234567890')
    ('isbn_', '1234567890')
    >>> split_key('ISBN1234567890123')
    ('isbn_', '1234567890123')
    >>> split_key('LCCNsa 64009056')
    ('lccn', 'sa 64009056')
    >>> split_key('badkey')
    (None, None)
    """
    bib_key = bib_key.strip()
    if not bib_key:
        return None, None

    valid_keys = ['isbn', 'lccn', 'oclc', 'ocaid', 'olid']
    key, value = None, None

    # split with : when possible
    if ':' in bib_key:
        key, value = bib_key.split(':', 1)
        key = key.lower()
    else:
        # try prefix match
        for k in valid_keys:
            if bib_key.lower().startswith(k):
                key = k
                value = bib_key[len(k) :]
                continue

    # treat plain number as ISBN
    if key is None and bib_key[0].isdigit():
        key = 'isbn'
        value = bib_key

    # treat OLxxxM as OLID
    re_olid = web.re_compile(r'OL\d+M(@\d+)?')
    if key is None and re_olid.match(bib_key.upper()):
        key = 'olid'
        value = bib_key.upper()

    if key == 'isbn':
        # 'isbn_' is a special indexed field that gets both isbn_10 and isbn_13 in the normalized form.
        key = 'isbn_'
        value = (value or "").replace("-", "")  # normalize isbn by stripping hyphens

    if key == 'oclc':
        key = 'oclc_numbers'

    if key == 'olid':
        key = 'key'
        value = '/books/' + (value or "").upper()

    return key, value


def ol_query(name, value):
    query = {
        'type': '/type/edition',
        name: value,
    }
    keys = web.ctx.site.things(query)
    if keys:
        return keys[0]


def ol_get_many_as_dict(keys: Iterable[str]) -> dict:
    """
    Ex.: ol_get_many_as_dict(['/books/OL2058361M', '/works/OL54120W'])
    """
    keys_with_revisions = [k for k in keys if '@' in k]
    keys2 = [k for k in keys if '@' not in k]

    result = {doc['key']: doc for doc in ol_get_many(keys2)}

    for k in keys_with_revisions:
        key, revision = k.split('@', 1)
        revision = h.safeint(revision, None)
        doc = web.ctx.site.get(key, revision)
        result[k] = doc and doc.dict()

    return result


def ol_get_many(keys: Iterable[str]) -> list:
    return [doc.dict() for doc in web.ctx.site.get_many(keys)]


def query_keys(bib_keys: Iterable[str]) -> dict:
    """Given a list of bibkeys, returns a mapping from bibkey to OL key.

    >> query(["isbn:1234567890"])
    {"isbn:1234567890": "/books/OL1M"}
    """

    def query(bib_key):
        name, value = split_key(bib_key)
        if name is None:
            return None
        elif name == 'key':
            return value
        else:
            return ol_query(name, value)

    d = {bib_key: query(bib_key) for bib_key in bib_keys}
    return {k: v for k, v in d.items() if v is not None}


def query_docs(bib_keys: Iterable[str]) -> dict:
    """Given a list of bib_keys, returns a mapping from bibkey to OL doc."""
    mapping = query_keys(bib_keys)
    thingdict = ol_get_many_as_dict(uniq(mapping.values()))
    return {
        bib_key: thingdict[key] for bib_key, key in mapping.items() if key in thingdict
    }


def uniq(values: Iterable[Hashable]) -> list:
    return list(set(values))


def process_result(result, jscmd):
    d = {
        "details": process_result_for_details,
        "data": DataProcessor().process,
        "viewapi": process_result_for_viewapi,
    }

    f = d.get(jscmd) or d['viewapi']
    return f(result)


def get_many_as_dict(keys: Iterable[str]) -> dict:
    return {doc['key']: doc for doc in ol_get_many(keys)}


def get_url(doc: Mapping[str, str]) -> str:
    base = web.ctx.get("home", "https://openlibrary.org")
    if base == 'http://[unknown]':
        base = "https://openlibrary.org"
    if doc['key'].startswith(("/books/", "/works/")):
        return base + doc['key'] + "/" + urlsafe(doc.get("title", "untitled"))
    elif doc['key'].startswith("/authors/"):
        return base + doc['key'] + "/" + urlsafe(doc.get("name", "unnamed"))
    else:
        return base + doc['key']


class DataProcessor:
    """Processor to process the result when jscmd=data."""

    def process(self, result):
        work_keys = [w['key'] for doc in result.values() for w in doc.get('works', [])]
        self.works = get_many_as_dict(work_keys)

        author_keys = [
            a['author']['key']
            for w in self.works.values()
            for a in w.get('authors', [])
        ]
        self.authors = get_many_as_dict(author_keys)

        return {k: self.process_doc(doc) for k, doc in result.items()}

    def get_authors(self, work):
        author_keys = [a['author']['key'] for a in work.get('authors', [])]
        return [
            {
                "url": get_url(self.authors[key]),
                "name": self.authors[key].get("name", ""),
            }
            for key in author_keys
        ]

    def get_work(self, doc):
        works = [self.works[w['key']] for w in doc.get('works', [])]
        if works:
            return works[0]
        else:
            return {}

    def process_doc(self, doc):
        """Processes one document.
        Should be called only after initializing self.authors and self.works.
        """
        w = self.get_work(doc)

        def subject(name, prefix):
            # handle bad subjects loaded earlier.
            if isinstance(name, dict):
                if 'value' in name:
                    name = name['value']
                elif 'key' in name:
                    name = name['key'].split("/")[-1].replace("_", " ")
                else:
                    return {}

            return {
                "name": name,
                "url": "https://openlibrary.org/subjects/{}{}".format(
                    prefix, name.lower().replace(" ", "_")
                ),
            }

        def get_subjects(name, prefix):
            return [subject(s, prefix) for s in w.get(name, '')]

        def get_value(v):
            if isinstance(v, dict):
                return v.get('value', '')
            else:
                return v

        def format_excerpt(e):
            return {
                "text": get_value(e.get("excerpt", {})),
                "comment": e.get("comment", ""),
            }

        def format_table_of_contents(toc):
            # after openlibrary.plugins.upstream.models.get_table_of_contents
            def row(r):
                if isinstance(r, str):
                    level = 0
                    label = ""
                    title = r
                    pagenum = ""
                else:
                    level = h.safeint(r.get('level', '0'), 0)
                    label = r.get('label', '')
                    title = r.get('title', '')
                    pagenum = r.get('pagenum', '')
                r = dict(level=level, label=label, title=title, pagenum=pagenum)
                return r

            d = [row(r) for r in toc]
            return [row for row in d if any(row.values())]

        d = {
            "url": get_url(doc),
            "key": doc['key'],
            "title": doc.get("title", ""),
            "subtitle": doc.get("subtitle", ""),
            "authors": self.get_authors(w),
            "number_of_pages": doc.get("number_of_pages", ""),
            "pagination": doc.get("pagination", ""),
            "weight": doc.get("weight", ""),
            "by_statement": doc.get("by_statement", ""),
            'identifiers': web.dictadd(
                doc.get('identifiers', {}),
                {
                    'isbn_10': doc.get('isbn_10', []),
                    'isbn_13': doc.get('isbn_13', []),
                    'lccn': doc.get('lccn', []),
                    'oclc': doc.get('oclc_numbers', []),
                    'openlibrary': [doc['key'].split("/")[-1]],
                },
            ),
            'classifications': web.dictadd(
                doc.get('classifications', {}),
                {
                    'lc_classifications': doc.get('lc_classifications', []),
                    'dewey_decimal_class': doc.get('dewey_decimal_class', []),
                },
            ),
            "publishers": [{"name": p} for p in doc.get("publishers", "")],
            "publish_places": [{"name": p} for p in doc.get("publish_places", "")],
            "publish_date": doc.get("publish_date"),
            "subjects": get_subjects("subjects", ""),
            "subject_places": get_subjects("subject_places", "place:"),
            "subject_people": get_subjects("subject_people", "person:"),
            "subject_times": get_subjects("subject_times", "time:"),
            "excerpts": [format_excerpt(e) for e in w.get("excerpts", [])],
            "notes": get_value(doc.get("notes", "")),
            "table_of_contents": format_table_of_contents(
                doc.get("table_of_contents", [])
            ),
            "links": [
                dict(title=link.get("title"), url=link['url'])
                for link in w.get('links', '')
                if link.get('url')
            ],
        }

        for fs in [doc.get("first_sentence"), w.get('first_sentence')]:
            if fs:
                e = {"text": get_value(fs), "comment": "", "first_sentence": True}
                d['excerpts'].insert(0, e)
                break

        def ebook(doc):
            itemid = doc['ocaid']
            availability = get_ia_availability(itemid)

            d = {
                "preview_url": "https://archive.org/details/" + itemid,
                "availability": availability,
                "formats": {},
            }

            prefix = f"https://archive.org/download/{itemid}/{itemid}"
            if availability == 'full':
                d["read_url"] = "https://archive.org/stream/%s" % (itemid)
                d['formats'] = {
                    "pdf": {"url": prefix + ".pdf"},
                    "epub": {"url": prefix + ".epub"},
                    "text": {"url": prefix + "_djvu.txt"},
                }
            elif availability == "borrow":
                d['borrow_url'] = "https://openlibrary.org{}/{}/borrow".format(
                    doc['key'], h.urlsafe(doc.get("title", "untitled"))
                )
                loanstatus = web.ctx.site.store.get(
                    'ebooks/' + doc['ocaid'], {'borrowed': 'false'}
                )
                d['checkedout'] = loanstatus['borrowed'] == 'true'

            return d

        if doc.get("ocaid"):
            d['ebooks'] = [ebook(doc)]

        if doc.get('covers'):
            cover_id = doc['covers'][0]
            d['cover'] = {
                "small": "https://covers.openlibrary.org/b/id/%s-S.jpg" % cover_id,
                "medium": "https://covers.openlibrary.org/b/id/%s-M.jpg" % cover_id,
                "large": "https://covers.openlibrary.org/b/id/%s-L.jpg" % cover_id,
            }

        d['identifiers'] = trim(d['identifiers'])
        d['classifications'] = trim(d['classifications'])
        return trim(d)


def trim(d):
    """Remote empty values from given dictionary.

    >>> trim({"a": "x", "b": "", "c": [], "d": {}})
    {'a': 'x'}
    """
    return {k: v for k, v in d.items() if v}


def get_authors(docs):
    """Returns a dict of author_key to {"key", "...", "name": "..."} for all authors in docs."""
    authors = [a['key'] for doc in docs for a in doc.get('authors', [])]
    author_dict = {}

    if authors:
        for a in ol_get_many(uniq(authors)):
            author_dict[a['key']] = {"key": a['key'], "name": a.get("name", "")}

    return author_dict


def process_result_for_details(result):
    def f(bib_key, doc):
        d = process_doc_for_viewapi(bib_key, doc)

        if 'authors' in doc:
            doc['authors'] = [author_dict[a['key']] for a in doc['authors']]

        d['details'] = doc
        return d

    author_dict = get_authors(result.values())
    return {k: f(k, doc) for k, doc in result.items()}


def process_result_for_viewapi(result):
    return {k: process_doc_for_viewapi(k, doc) for k, doc in result.items()}


def get_ia_availability(itemid):
    collections = ia.get_metadata(itemid).get('collection', [])

    if 'lendinglibrary' in collections or 'inlibrary' in collections:
        return 'borrow'
    elif 'printdisabled' in collections:
        return 'restricted'
    else:
        return 'full'


def process_doc_for_viewapi(bib_key, page):
    key = page['key']

    url = get_url(page)

    if 'ocaid' in page:
        preview = get_ia_availability(page['ocaid'])
        preview_url = 'https://archive.org/details/' + page['ocaid']
    else:
        preview = 'noview'
        preview_url = url

    d = {
        'bib_key': bib_key,
        'info_url': url,
        'preview': preview,
        'preview_url': preview_url,
    }

    if page.get('covers'):
        d['thumbnail_url'] = (
            'https://covers.openlibrary.org/b/id/%s-S.jpg' % page["covers"][0]
        )

    return d


def format_result(result, options):
    """Format result as js or json.

    >>> format_result({'x': 1}, {})
    'var _OLBookInfo = {"x": 1};'
    >>> format_result({'x': 1}, {'callback': 'f'})
    '{"x": 1}'
    """
    format = options.get('format', '').lower()
    if format == 'json':
        return json.dumps(result)
    else:  # js
        json_data = json.dumps(result)
        callback = options.get("callback")
        if callback:
            # the API handles returning the data as a callback
            return "%s" % json_data
        else:
            return "var _OLBookInfo = %s;" % json_data


def dynlinks(bib_keys, options):
    # for backward-compatibility
    if options.get("details", "").lower() == "true":
        options["jscmd"] = "details"

    try:
        result = query_docs(bib_keys)
        result = process_result(result, options.get('jscmd'))
    except:
        print("Error in processing Books API", file=sys.stderr)
        register_exception()

        result = {}
    return format_result(result, options)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
