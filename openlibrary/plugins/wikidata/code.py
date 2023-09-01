"""
The purpose of this file is to:
1. Interact with the Wikidata API
2. Store the results
3. Make the results easy to access from other files
"""
import requests
from dataclasses import dataclass

from openlibrary.core.wikidata import WikidataEntities


@dataclass
class WikiDataEntity:
    id: str
    descriptions: dict[str, str]

    def description(self, language: str = 'en') -> str | None:
        return self.descriptions[language]


def get_wikidata_entity(QID: str) -> WikiDataEntity:
    if entity := WikidataEntities.get_by_id(QID):
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
