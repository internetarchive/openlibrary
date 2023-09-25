"""
The purpose of this file is to:
1. Interact with the Wikidata API
2. Store the results
3. Make the results easy to access from other files
"""
import requests
import web
from dataclasses import dataclass
from openlibrary.core.helpers import days_since

from datetime import datetime
import json
from openlibrary.core import db


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
        return cls(
            type=data.get('type'),
            labels=data.get('labels'),
            descriptions=data.get('descriptions'),
            aliases=data.get('aliases'),
            statements=data.get('statements'),
            sitelinks=data.get('sitelinks'),
            id=data.get('id'),
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
    def from_db_query(cls, data: web.utils.Storage):
        return cls(
            id=data.id,
            data=data.data,
            updated=data.updated,
        )


def _get_from_web(id: str) -> WikiDataEntity | None:
    response = requests.get(
        f'https://www.wikidata.org/w/rest.php/wikibase/v0/entities/items/{id}'
    )
    if response.status_code == 200:
        response_json = response.json()
        _add_to_cache(id=id, data=response_json)
        return WikiDataEntity(
            id=id,
            data=WikiDataAPIResponse.from_dict(response_json),
            updated=datetime.now(),
        )
    else:
        return None
    # TODO: What should we do in non-200 cases?
    # They're documented here https://doc.wikimedia.org/Wikibase/master/js/rest-api/


def get_wikidata_entity(QID: str, ttl_days: int = 30) -> WikiDataEntity | None:
    """
    This only supports QIDs, if we want to support PIDs we need to use different endpoints
    ttl (time to live) inspired by the cachetools api https://cachetools.readthedocs.io/en/latest/#cachetools.TTLCache
    """

    entity = _get_from_cache(QID)
    if entity and days_since(entity.updated) < ttl_days:
        return WikiDataEntity(
            id=QID,
            data=WikiDataAPIResponse.from_dict(entity.data),
            updated=datetime.now(),
        )
    else:
        return _get_from_web(QID)


class WikidataRow:
    id: str
    data: dict
    updated: datetime


def _get_from_cache_by_ids(ids: list[str]) -> list[WikidataRow]:
    # TODO: convert to WikidataRow ?
    return list(
        db.get_db().query(
            'select * from wikidata where id IN ($ids)',
            vars={'ids': ids},
        )
    )


def _get_from_cache(id: str) -> WikiDataEntity | None:
    if len(result := _get_from_cache_by_ids([id])) > 0:
        return result[0]
    return None


# TODO: typehint the data?
def _add_to_cache(id: str, data: dict) -> None:
    # TODO: when we upgrade to postgres 9.5+ we should use upsert here
    oldb = db.get_db()
    json_data = json.dumps(data)

    if _get_from_cache(id):
        return oldb.update("wikidata", where="id=$id", vars={'id': id}, data=json_data)
    else:
        return oldb.insert("wikidata", id=id, data=json_data)
