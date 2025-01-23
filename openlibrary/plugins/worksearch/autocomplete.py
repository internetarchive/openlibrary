import itertools
import json
from collections.abc import Iterable

import web

from infogami.utils import delegate
from infogami.utils.view import safeint
from openlibrary.core.models import Thing
from openlibrary.plugins.upstream import utils
from openlibrary.plugins.worksearch.search import get_solr
from openlibrary.utils import (
    find_olid_in_string,
    olid_to_key,
)


def to_json(d):
    web.header('Content-Type', 'application/json')
    return delegate.RawText(json.dumps(d))


class autocomplete(delegate.page):
    path = "/_autocomplete"
    fq = ('-type:edition',)
    fl = 'key,type,name,title,score'
    olid_suffix: str | None = None
    sort: str | None = None
    query = 'title:"{q}"^2 OR title:({q}*) OR name:"{q}"^2 OR name:({q}*)'

    def db_fetch(self, key: str) -> Thing | None:
        if thing := web.ctx.site.get(key):
            return thing.as_fake_solr_record()
        else:
            return None

    def doc_wrap(self, doc: dict):
        """Modify the returned solr document in place."""
        if 'name' not in doc:
            doc['name'] = doc.get('title')

    def doc_filter(self, doc: dict) -> bool:
        """Exclude certain documents"""
        return True

    def GET(self):
        return self.direct_get()

    def direct_get(self, fq: Iterable[str] | None = None):
        i = web.input(q="", limit=5)
        i.limit = safeint(i.limit, 5)

        solr = get_solr()

        # look for ID in query string here
        q = solr.escape(i.q).strip()
        embedded_olid = None
        if self.olid_suffix:
            embedded_olid = find_olid_in_string(q, self.olid_suffix)

        if embedded_olid:
            solr_q = f'key:"{olid_to_key(embedded_olid)}"'
        else:
            solr_q = self.query.format(q=q)

        fq = fq or self.fq
        params = {
            'q_op': 'AND',
            'rows': i.limit,
            **({'fq': fq} if fq else {}),
            # limit the fields returned for better performance
            'fl': self.fl,
            **({'sort': self.sort} if self.sort else {}),
        }

        data = solr.select(solr_q, **params)
        docs = data['docs']

        if embedded_olid and not docs:
            # Grumble! Work not in solr yet. Create a dummy.
            fake_doc = self.db_fetch(olid_to_key(embedded_olid))
            if fake_doc:
                docs = [fake_doc]

        result_docs = []
        for d in docs:
            if self.doc_filter(d):
                self.doc_wrap(d)
                result_docs.append(d)

        return to_json(result_docs)


class languages_autocomplete(delegate.page):
    path = "/languages/_autocomplete"

    def GET(self):
        i = web.input(q="", limit=5)
        i.limit = safeint(i.limit, 5)
        web.header("Cache-Control", "max-age=%d" % (24 * 3600))
        return to_json(
            list(itertools.islice(utils.autocomplete_languages(i.q), i.limit))
        )


class works_autocomplete(autocomplete):
    path = "/works/_autocomplete"
    fq = ('type:work',)
    fl = 'key,title,subtitle,cover_i,first_publish_year,author_name,edition_count'
    olid_suffix = 'W'
    query = 'title:"{q}"^2 OR title:({q}*)'

    def doc_filter(self, doc: dict) -> bool:
        # Exclude orphaned editions from autocomplete results
        # Note: Do this here instead of with an `fq=key:*W` for performance
        # reasons.
        return doc['key'][-1] == 'W'

    def doc_wrap(self, doc: dict):
        doc['full_title'] = doc['title']
        if 'subtitle' in doc:
            doc['full_title'] += ": " + doc['subtitle']
        doc['name'] = doc.get('title')


class authors_autocomplete(autocomplete):
    path = "/authors/_autocomplete"
    fq = ('type:author',)
    fl = 'key,name,alternate_names,birth_date,death_date,work_count,top_work,top_subjects'
    olid_suffix = 'A'
    query = 'name:({q}*) OR alternate_names:({q}*) OR name:"{q}"^2 OR alternate_names:"{q}"^2'

    def doc_wrap(self, doc: dict):
        if 'top_work' in doc:
            doc['works'] = [doc.pop('top_work')]
        else:
            doc['works'] = []
        doc['subjects'] = doc.pop('top_subjects', [])


class subjects_autocomplete(autocomplete):
    # can't use /subjects/_autocomplete because the subjects endpoint = /subjects/[^/]+
    path = "/subjects_autocomplete"
    fq = ('type:subject',)
    fl = 'key,name,work_count'
    query = 'name:({q}*)'
    sort = 'work_count desc'

    def GET(self):
        i = web.input(type="")
        fq = self.fq
        if i.type:
            fq = fq + (f'subject_type:{i.type}',)

        return super().direct_get(fq=fq)


def setup():
    """Do required setup."""
    pass
