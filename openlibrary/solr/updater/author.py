from typing import cast
import httpx
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.updater.abstract import AbstractSolrUpdater
from openlibrary.solr.utils import SolrUpdateRequest, get_solr_base_url


class AuthorSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/authors/'
    thing_type = '/type/author'

    async def update_key(self, author: dict) -> tuple[SolrUpdateRequest, list[str]]:
        author_id = author['key'].split("/")[-1]
        facet_fields = ['subject', 'time', 'person', 'place']
        base_url = get_solr_base_url() + '/select'

        async with httpx.AsyncClient() as client:
            response = await client.get(
                base_url,
                params=[  # type: ignore[arg-type]
                    ('wt', 'json'),
                    ('json.nl', 'arrarr'),
                    ('q', 'author_key:%s' % author_id),
                    ('sort', 'edition_count desc'),
                    ('rows', 1),
                    ('fl', 'title,subtitle'),
                    ('facet', 'true'),
                    ('facet.mincount', 1),
                ]
                + [('facet.field', '%s_facet' % field) for field in facet_fields],
            )
            reply = response.json()
        work_count = reply['response']['numFound']
        docs = reply['response'].get('docs', [])
        top_work = None
        if docs and docs[0].get('title', None):
            top_work = docs[0]['title']
            if docs[0].get('subtitle', None):
                top_work += ': ' + docs[0]['subtitle']
        all_subjects = []
        for f in facet_fields:
            for s, num in reply['facet_counts']['facet_fields'][f + '_facet']:
                all_subjects.append((num, s))
        all_subjects.sort(reverse=True)
        top_subjects = [s for num, s in all_subjects[:10]]
        d = cast(
            SolrDocument,
            {
                'key': f'/authors/{author_id}',
                'type': 'author',
            },
        )

        if author.get('name', None):
            d['name'] = author['name']

        alternate_names = author.get('alternate_names', [])
        if alternate_names:
            d['alternate_names'] = alternate_names

        if author.get('birth_date', None):
            d['birth_date'] = author['birth_date']
        if author.get('death_date', None):
            d['death_date'] = author['death_date']
        if author.get('date', None):
            d['date'] = author['date']

        if top_work:
            d['top_work'] = top_work
        d['work_count'] = work_count
        d['top_subjects'] = top_subjects

        return SolrUpdateRequest(adds=[d]), []
