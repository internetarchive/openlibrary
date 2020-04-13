"""Search utilities.
"""
from openlibrary.utils.solr import Solr
from infogami import config
from infogami.utils import stats
import web
import logging


def get_solr():
    base_url = "http://%s/solr" % config.plugin_worksearch.get('solr')
    return Solr(base_url)

def work_search(query, limit=20, offset=0, **kw):
    """Search for works."""

    kw.setdefault("doc_wrapper", work_wrapper)
    kw.setdefault("fq", "type:work")

    fields = [
        "key",
        "author_name",
        "author_key",
        "title",
        "edition_count",
        "ia",
        "cover_edition_key",
        "has_fulltext",
        "subject",
        "ia_collection_s",
        "public_scan_b",
        "lending_edition_s",
        "lending_identifier_s",
    ]
    kw.setdefault("fields", fields)

    query = process_work_query(query)
    solr = get_solr()

    stats.begin("solr", query=query, start=offset, rows=limit, kw=kw)
    try:
        result = solr.select(query, start=offset, rows=limit, **kw)
    except Exception as e:
        logging.getLogger("openlibrary").exception("Failed solr query")
        return None
    finally:
        stats.end()

    return result

def process_work_query(query):
    if "author" in query and isinstance(query["author"], dict):
        author = query.pop("author")
        query["author_key"] = author["key"]

    ebook = query.pop("ebook", None)
    if ebook == True or ebook == "true":
        query["has_fulltext"] = "true"

    return query

def work_wrapper(w):
    key = w['key']
    if not key.startswith("/works/"):
        key += "/works/"

    d = web.storage(
        key=key,
        title=w["title"],
        edition_count=w["edition_count"]
    )

    if "cover_id" in w:
        d.cover_id = w["cover_id"]
    elif "cover_edition_key" in w:
        book = web.ctx.site.get("/books/" + w["cover_edition_key"])
        cover = book and book.get_cover()
        d.cover_id = cover and cover.id or None
        d.cover_edition_key = w['cover_edition_key']
    else:
        d.cover_id = None
    d.subject = w.get('subject', [])
    ia_collection = w['ia_collection_s'].split(';') if 'ia_collection_s' in w else []
    d.ia_collection = ia_collection
    d.lendinglibrary = 'lendinglibrary' in ia_collection
    d.printdisabled = 'printdisabled' in ia_collection
    d.lending_edition = w.get('lending_edition_s', '')
    d.lending_identifier = w.get('lending_identifier_s', '')

    # special care to handle missing author_key/author_name in the solr record
    w.setdefault('author_key', [])
    w.setdefault('author_name', [])

    d.authors = [web.storage(key='/authors/' + k, name=n)
                 for k, n in zip(w['author_key'], w['author_name'])]

    d.first_publish_year = (w['first_publish_year'][0] if 'first_publish_year' in w else None)
    d.ia = w.get('ia', [])
    d.public_scan = w.get('public_scan_b', bool(d.ia))
    d.has_fulltext = w.get('has_fulltext', "false")
    return d
