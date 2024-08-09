import itertools
import web
import json


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
    fq = ['-type:edition']
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

    def direct_get(self, fq: list[str] | None = None, exclude_subjects=None, exclude_authors=None, exclude_languages=None, exclude_publishers=None):
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
        if exclude_subjects:
            fq.append(f'-subject:({" OR ".join(exclude_subjects)})')
        if exclude_authors:
            fq.append(f'-author_key:({" OR ".join(exclude_authors)})')
        if exclude_languages:
            fq.append(f'-language:({" OR ".join(exclude_languages)})')
        if exclude_publishers:
            fq.append(f'-publisher_facet:({" OR ".join(exclude_publishers)})')

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


class author_autocomplete(autocomplete):
    fq = ['+type:author']
    fl = 'key,name,alternate_names,birth_date,death_date,date,top_work,work_count,top_subjects'
    olid_suffix = 'OL..A'
    query = 'name:"{q}"^2 OR name:({q}*) OR alternate_names:({q}*)'

    def doc_wrap(self, doc: dict):
        doc['name'] = doc.get('name', '')
        doc['top_subjects'] = doc.get('top_subjects', [])
        doc['birth_date'] = doc.get('birth_date') or doc.get('date')


class subject_autocomplete(autocomplete):
    fq = ['+type:subject']
    fl = 'key,name,subject_type,work_count'
    olid_suffix = 'OL..S'
    query = 'name:"{q}"^2 OR name:({q}*)'


class work_autocomplete(autocomplete):
    fq = ['+type:work']
    fl = 'key,title,subtitle,cover_i,first_publish_year,author_name,edition_count,cover_edition_key'
    olid_suffix = 'OL..W'
    query = 'title:"{q}"^2 OR title:({q}*)'

    def doc_wrap(self, doc: dict):
        doc['name'] = doc.get('title', '')
        doc['authors'] = [{'name': n} for n in doc.get('author_name', [])]


class edition_autocomplete(autocomplete):
    fq = ['+type:edition']
    fl = 'key,title,subtitle,publishers,publish_year,isbn,last_modified_i,cover_i,cover_edition_key,author_name'
    olid_suffix = 'OL..M'
    query = 'title:"{q}"^2 OR title:({q}*)'

    def doc_wrap(self, doc: dict):
        doc['name'] = doc.get('title', '')
        doc['authors'] = [{'name': n} for n in doc.get('author_name', [])]


class list_autocomplete(autocomplete):
    fq = ['+type:list']
    fl = 'key,name,description,seed_count,last_update'
    olid_suffix = 'OL..L'
    query = 'name:"{q}"^2 OR name:({q}*)'


def setup():
    pass