"""
First pass for incorporating wikidata into OpenLibrary author Pages.

TODO:
- Cache responses from Wikidata (preferably in a table)

"""
import requests
from dataclasses import dataclass


@dataclass
class WikiDataEntity:
    descriptions: dict[str, str]

    def description(self, language: str = 'en') -> str | None:
        return self.descriptions[language]


def get_wikidata_entity(QID: str) -> WikiDataEntity:
    response = requests.get(
        "https://www.wikidata.org/w/rest.php/wikibase/v0/entities/items/" + QID
    ).json()
    return WikiDataEntity(descriptions=response["descriptions"])
