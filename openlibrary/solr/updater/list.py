import re
from collections import defaultdict
from typing import cast

import httpx

from openlibrary.plugins.openlibrary.lists import (
    SeedType,
    seed_key_to_seed_type,
)
from openlibrary.plugins.worksearch.subjects import SubjectType
from openlibrary.solr.solr_types import SolrDocument
from openlibrary.solr.updater.abstract import AbstractSolrBuilder, AbstractSolrUpdater
from openlibrary.solr.utils import SolrUpdateRequest, get_solr_base_url, str_to_key


class ListSolrUpdater(AbstractSolrUpdater):
    key_prefix = '/lists/'
    thing_type = '/type/list'

    def key_test(self, key: str) -> bool:
        return bool(re.match(r'^(/people/[^/]+)?/lists/[^/]+$', key))

    async def update_key(self, list: dict) -> tuple[SolrUpdateRequest, list[str]]:
        seeds = ListSolrBuilder(list).seed
        lst = ListSolrBuilder(list, await fetch_seeds_facets(seeds))
        doc = lst.build()
        return SolrUpdateRequest(adds=[doc]), []


async def fetch_seeds_facets(seeds: list[str]):
    base_url = get_solr_base_url() + '/select'
    facet_fields: list[SubjectType] = ['subject', 'time', 'person', 'place']

    seeds_by_type: defaultdict[SeedType, list] = defaultdict(list)
    for seed in seeds:
        seeds_by_type[seed_key_to_seed_type(seed)].append(seed)

    query: list[str] = []
    for seed_type, seed_values in seeds_by_type.items():
        match seed_type:
            case 'edition' | 'author':
                edition_olids = " OR ".join(key.split('/')[-1] for key in seed_values)
                query.append(f'edition_key:( {edition_olids} )')
            case 'work':
                seed_keys = " OR ".join(f'"{key}"' for key in seed_values)
                query.append(f'key:( {seed_keys} )')
            case 'subject':
                pass
            case _:
                raise NotImplementedError(f'Unknown seed type {seed_type}')

    async with httpx.AsyncClient() as client:
        response = await client.post(
            base_url,
            timeout=30,
            data={
                'wt': 'json',
                'json.nl': 'arrarr',
                'q': ' OR '.join(query),
                'fq': 'type:work',
                'rows': 0,
                'facet': 'true',
                'facet.mincount': 1,
                'facet.limit': 50,
                'facet.field': [f"{field}_facet" for field in facet_fields],
            },
        )
        return response.json()


class ListSolrBuilder(AbstractSolrBuilder):
    def __init__(self, list: dict, solr_reply: dict | None = None):
        self._list = list
        self._solr_reply = solr_reply

    def build(self) -> SolrDocument:
        doc = cast(dict, super().build())
        doc |= self.build_subjects()
        return cast(SolrDocument, doc)

    def build_subjects(self) -> dict:
        if not self._solr_reply:
            return {}

        doc: dict = {}
        for facet, counts in self._solr_reply['facet_counts']['facet_fields'].items():
            subject_type = cast(SubjectType, facet.split('_')[0])
            subjects = [s for s, count in counts]
            doc |= {
                subject_type: subjects,
                f'{subject_type}_facet': subjects,
                f'{subject_type}_key': [str_to_key(s) for s in subjects],
            }
        return doc

    @property
    def key(self) -> str:
        return self._list['key']

    @property
    def type(self) -> str:
        return 'list'

    @property
    def name(self) -> str | None:
        return self._list.get('name')

    @property
    def seed(self) -> list[str]:
        return [
            (
                (seed.get('key') or seed['thing']['key'])
                if isinstance(seed, dict)
                else seed
            )
            for seed in self._list.get('seeds', [])
        ]
