"""
First pass for incorporating wikidata into OpenLibrary author Pages.

TODO:
- Cache responses from Wikidata (preferably in a table)

"""
import requests
from dataclasses import dataclass

from openlibrary.core.wikidata import WikidataEntities


@dataclass
class WikiDataEntity:
    descriptions: dict[str, str]

    def description(self, language: str = 'en') -> str | None:
        return self.descriptions[language]


def get_wikidata_entity(QID: str) -> WikiDataEntity:
    entity = WikidataEntities.get_by_id(QID)
    if not entity:
        response = requests.get(
            'https://www.wikidata.org/w/rest.php/wikibase/v0/entities/items/{QID}'
        ).json()
        # TODO check for 200?
        WikidataEntities.add(QID, response)
        return WikiDataEntity(descriptions=response["descriptions"])
    else:
        return WikiDataEntity(descriptions=entity["descriptions"])
