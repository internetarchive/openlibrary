"""
The purpose of this file is to:
1. Interact with the Wikidata API
2. Store the results
3. Make the results easy to access from other files
"""
import requests
import web
import dataclasses
from dataclasses import dataclass
from openlibrary.core.helpers import days_since

from datetime import datetime
import json
from openlibrary.core import db

WIKIDATA_CACHE_TTL_DAYS = 30


@dataclass
class WikiDataAPIResponse:
    type: str
    labels: dict
    descriptions: dict
    aliases: dict
    statements: dict
    sitelinks: dict
    id: str

    @classmethod
    def from_dict(cls, data: dict):
        # use [''] instead of get so this fails if fields are missing
        return cls(
            type=data['type'],
            labels=data['labels'],
            descriptions=data['descriptions'],
            aliases=data['aliases'],
            statements=data['statements'],
            sitelinks=data['sitelinks'],
            id=data['id'],
        )


@dataclass
class WikiDataEntity:
    id: str
    data: WikiDataAPIResponse
    updated: datetime

    def description(self, language: str = 'en') -> str | None:
        """If a description isn't available in the requested language default to English"""
        return self.data.descriptions.get(language) or self.data.descriptions.get('en')

    @classmethod
    def from_db_query(cls, response: web.utils.Storage):
        return cls(
            id=response.id,
            data=WikiDataAPIResponse.from_dict(response.data),
            updated=response.updated,
        )

    @classmethod
    def from_web(cls, response: dict):
        data = WikiDataAPIResponse.from_dict(response)
        return cls(
            id=data.id,
            data=data,
            updated=datetime.now(),
        )


def get_wikidata_entity(QID: str, use_cache: bool = True) -> WikiDataEntity | None:
    """
    This only supports QIDs, if we want to support PIDs we need to use different endpoints
    ttl (time to live) inspired by the cachetools api https://cachetools.readthedocs.io/en/latest/#cachetools.TTLCache
    """

    entity = _get_from_cache(QID)
    if entity and use_cache and days_since(entity.updated) < WIKIDATA_CACHE_TTL_DAYS:
        return entity
    else:
        return _get_from_web(QID)


def _get_from_web(id: str) -> WikiDataEntity | None:
    response = requests.get(
        f'https://www.wikidata.org/w/rest.php/wikibase/v0/entities/items/{id}'
    )
    if response.status_code == 200:
        entity = WikiDataEntity.from_web(response.json())
        _add_to_cache(entity)
        return entity
    else:
        return None
    # TODO: What should we do in non-200 cases?
    # They're documented here https://doc.wikimedia.org/Wikibase/master/js/rest-api/


def _get_from_cache_by_ids(ids: list[str]) -> list[WikiDataEntity]:
    response = list(
        db.get_db().query(
            'select * from wikidata where id IN ($ids)',
            vars={'ids': ids},
        )
    )
    return [WikiDataEntity.from_db_query(r) for r in response]


def _get_from_cache(id: str) -> WikiDataEntity | None:
    """
    The cache is OpenLibrary's Postgres instead of calling the Wikidata API
    """
    if len(result := _get_from_cache_by_ids([id])) > 0:
        return result[0]
    return None


def _add_to_cache(entity: WikiDataEntity) -> None:
    # TODO: when we upgrade to postgres 9.5+ we should use upsert here
    oldb = db.get_db()
    json_data = json.dumps(dataclasses.asdict(entity.data))

    if _get_from_cache(entity.id):
        return oldb.update(
            "wikidata", where="id=$id", vars={'id': entity.id}, data=json_data
        )
    else:
        return oldb.insert("wikidata", id=entity.id, data=json_data)
