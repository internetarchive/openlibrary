"""Search utilities.
"""
from openlibrary.utils.solr import Solr
from infogami import config
import web


def get_solr():
    base_url = config.plugin_worksearch.get('solr_base_url')
    return Solr(base_url)


def work_wrapper(w: dict) -> web.storage:
    ia_collection = w.get('ia_collection_s', '').split(';')
    return web.storage(
        key=w['key'],
        title=w["title"],
        edition_count=w["edition_count"],
        cover_id=w.get('cover_i'),
        cover_edition_key=w.get('cover_edition_key'),
        subject=w.get('subject', []),
        ia_collection=ia_collection,
        lendinglibrary='lendinglibrary' in ia_collection,
        printdisabled='printdisabled' in ia_collection,
        lending_edition=w.get('lending_edition_s', ''),
        lending_identifier=w.get('lending_identifier_s', ''),
        authors=[
            web.storage(key=f'/authors/{olid}', name=name)
            for olid, name in zip(w.get('author_key', []), w.get('author_name', []))
        ],
        first_publish_year=w.get('first_publish_year'),
        ia=w.get('ia', [None])[0],
        public_scan=w.get('public_scan_b', bool(w.get('ia'))),
        has_fulltext=w.get('has_fulltext', False),
    )
