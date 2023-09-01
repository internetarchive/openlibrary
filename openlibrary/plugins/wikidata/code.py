"""
The purpose of this file is to:
1. Interact with the Wikidata API
2. Store the results
3. Make the results easy to access from other files
"""
import requests
from dataclasses import dataclass
from openlibrary.core.helpers import seconds_since

from openlibrary.core.wikidata import WikidataEntities

MONTH_IN_SECONDS = 60 * 60 * 24 * 30


@dataclass
class WikiDataEntity:
    id: str
    descriptions: dict[str, str]

    def description(self, language: str = 'en') -> str | None:
        # If a description isn't available in the requested language default to English
        return self.descriptions.get(language) or self.descriptions.get('en')


# ttl (time to live) inspired by the cachetools api https://cachetools.readthedocs.io/en/latest/#cachetools.TTLCache
def get_wikidata_entity(QID: str, ttl: int = MONTH_IN_SECONDS) -> WikiDataEntity | None:
    entity = WikidataEntities.get_by_id(QID)
    if entity and seconds_since(entity.updated) < ttl:
        return WikiDataEntity(
            id=entity.data["id"], descriptions=entity.data["descriptions"]
        )
    else:
        response = requests.get(
            'https://www.wikidata.org/w/rest.php/wikibase/v0/entities/items/{QID}'
        ).json()
        # TODO check for 200?
        WikidataEntities.add(QID, response)
        return WikiDataEntity(id=response["id"], descriptions=response["descriptions"])
