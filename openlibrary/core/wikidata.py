"""
The purpose of this file is to:
1. Interact with the Wikidata API
2. Store the results
3. Make the results easy to access from other files
"""

import requests
import logging
from dataclasses import dataclass
from openlibrary.core.helpers import days_since

from datetime import datetime
import json
from openlibrary.core import db

logger = logging.getLogger("core.wikidata")

WIKIDATA_API_URL = 'https://www.wikidata.org/w/rest.php/wikibase/v0/entities/items/'
WIKIDATA_CACHE_TTL_DAYS = 30

SOCIAL_PROFILES = [
    {
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/5/5e/ResearchGate_icon_SVG.svg",
        "wikidata_property": "P2038",
        "label": "ResearchGate",
        "base_url": "https://www.researchgate.net/profile/",
    },
    {
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/0/06/ORCID_iD.svg",
        "wikidata_property": "P496",
        "label": "ORCID",
        "base_url": "https://orcid.org/",
    },
    {
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/c/c7/Google_Scholar_logo.svg",
        "wikidata_property": "P1960",
        "label": "Google Scholar",
        "base_url": "https://scholar.google.com/citations?user=",
    },
    {
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/6/66/Academia-logo-2021.svg",
        "wikidata_property": "P5715",
        "label": "Academia.edu",
        "base_url": "",
    },
    {
        "icon_url": "https://avatars.githubusercontent.com/u/2212508",
        "wikidata_property": "P6005",
        "label": "Muck Rack",
        "base_url": "https://muckrack.com/",
    },
    {
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/d/d5/Mastodon_logotype_%28simple%29_new_hue.svg",
        "wikidata_property": "P4033",
        "label": "Mastodon",
        "base_url": "https://fedirect.toolforge.org/?id=",
    },
    {
        "icon_url": "https://play-lh.googleusercontent.com/XXqfqs9irPSjphsMPcC-c6Q4-FY5cd8klw4IdI2lof_Ie-yXaFirqbNDzK2kJ808WXJk",
        "wikidata_property": "P4985",
        "label": "TMDB",
        "base_url": "https://www.themoviedb.org/person/",
    },
    {
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/c/cb/Cib-imdb_%28CoreUI_Icons_v1.0.0%29.svg",
        "wikidata_property": "P345",
        "label": "IMDb",
        "base_url": "https://www.imdb.com/name/",
    },
    {
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/c/ce/X_logo_2023.svg",
        "wikidata_property": "P2002",
        "label": "X (Twitter)",
        "base_url": "https://twitter.com/",
    },
]


@dataclass
class WikidataEntity:
    """
    This is the model of the api response from WikiData plus the updated field
    https://www.wikidata.org/wiki/Wikidata:REST_API
    """

    id: str
    type: str
    labels: dict[str, str]
    descriptions: dict[str, str]
    aliases: dict[str, list[str]]
    statements: dict[str, list[dict]]
    sitelinks: dict[str, dict]
    _updated: datetime  # This is when we fetched the data, not when the entity was changed in Wikidata

    def get_description(self, language: str = 'en') -> str | None:
        """If a description isn't available in the requested language default to English"""
        return self.descriptions.get(language) or self.descriptions.get('en')

    def get_wikipedia_link(self, language: str = 'en') -> tuple[str, str] | None:
        """
        Get the Wikipedia URL and language for a given language code.
        Falls back to English if requested language is unavailable.
        """
        requested_wiki = f'{language}wiki'
        english_wiki = 'enwiki'

        if requested_wiki in self.sitelinks:
            return self.sitelinks[requested_wiki]['url'], language
        elif english_wiki in self.sitelinks:
            return self.sitelinks[english_wiki]['url'], 'en'
        return None

    @classmethod
    def from_dict(cls, response: dict, updated: datetime):
        return cls(
            **response,
            _updated=updated,
        )

    def to_wikidata_api_json_format(self) -> str:
        """
        Transforms the dataclass a JSON string like we get from the Wikidata API.
        This is used for storing the json in the database.
        """
        entity_dict = {
            'id': self.id,
            'type': self.type,
            'labels': self.labels,
            'descriptions': self.descriptions,
            'aliases': self.aliases,
            'statements': self.statements,
            'sitelinks': self.sitelinks,
        }
        return json.dumps(entity_dict)

    def get_statement_values(self, property_id: str) -> list[str]:
        """
        Get all values for a given property statement (e.g., P2038).
        Returns an empty list if the property doesn't exist.
        """
        if property_id not in self.statements:
            return []

        return [
            statement["value"]["content"]
            for statement in self.statements[property_id]
            if "value" in statement and "content" in statement["value"]
        ]

    def get_wiki_profiles_to_render(self, language: str) -> list[dict]:
        """
        Get formatted Wikipedia and Wikidata profile data for rendering.

        Args:
            language: The preferred language code (e.g., 'en')

        Returns:
            List of dicts containing url, icon_url, and label for Wikipedia and Wikidata profiles
        """
        profiles = []

        # Add Wikipedia link if available
        if wiki_link := self.get_wikipedia_link(language):
            url, lang = wiki_link
            label = "Wikipedia" if lang == language else f"Wikipedia (in {lang})"
            profiles.append(
                {
                    "url": url,
                    "icon_url": "https://upload.wikimedia.org/wikipedia/en/8/80/Wikipedia-logo-v2.svg",
                    "label": label,
                }
            )

        # Add Wikidata link
        profiles.append(
            {
                "url": f"https://www.wikidata.org/wiki/{self.id}",
                "icon_url": "https://upload.wikimedia.org/wikipedia/en/8/80/Wikipedia-logo-v2.svg",
                "label": "Wikidata",
            }
        )

        return profiles

    def get_profiles_to_render(self) -> list[dict]:
        """
        Get formatted social profile data for all configured social profiles.

        Returns:
            List of dicts containing url, icon_url, and label for all social profiles
        """
        profiles = []
        for profile_config in SOCIAL_PROFILES:
            values = self.get_statement_values(profile_config["wikidata_property"])
            profiles.extend(
                [
                    {
                        "url": f"{profile_config['base_url']}{value}",
                        "icon_url": profile_config["icon_url"],
                        "label": profile_config["label"],
                    }
                    for value in values
                ]
            )
        return profiles


def _cache_expired(entity: WikidataEntity) -> bool:
    return days_since(entity._updated) > WIKIDATA_CACHE_TTL_DAYS


def get_wikidata_entity(
    qid: str, bust_cache: bool = False, fetch_missing: bool = False
) -> WikidataEntity | None:
    """
    This only supports QIDs, if we want to support PIDs we need to use different endpoints
    By default this will only use the cache (unless it is expired).
    This is to avoid overwhelming Wikidata servers with requests from every visit to an author page.
    bust_cache must be set to True if you want to fetch new items from Wikidata.
    # TODO: After bulk data imports we should set fetch_missing to true (or remove it).
    """
    if bust_cache:
        return _get_from_web(qid)

    if entity := _get_from_cache(qid):
        if _cache_expired(entity):
            return _get_from_web(qid)
        return entity
    elif fetch_missing:
        return _get_from_web(qid)

    return None


def _get_from_web(id: str) -> WikidataEntity | None:
    response = requests.get(f'{WIKIDATA_API_URL}{id}')
    if response.status_code == 200:
        entity = WikidataEntity.from_dict(
            response=response.json(), updated=datetime.now()
        )
        _add_to_cache(entity)
        return entity
    else:
        logger.error(f'Wikidata Response: {response.status_code}, id: {id}')
        return None
    # Responses documented here https://doc.wikimedia.org/Wikibase/master/js/rest-api/


def _get_from_cache_by_ids(ids: list[str]) -> list[WikidataEntity]:
    response = list(
        db.get_db().query(
            'select * from wikidata where id IN ($ids)',
            vars={'ids': ids},
        )
    )
    return [
        WikidataEntity.from_dict(response=r.data, updated=r.updated) for r in response
    ]


def _get_from_cache(id: str) -> WikidataEntity | None:
    """
    The cache is OpenLibrary's Postgres instead of calling the Wikidata API
    """
    if result := _get_from_cache_by_ids([id]):
        return result[0]
    return None


def _add_to_cache(entity: WikidataEntity) -> None:
    # TODO: after we upgrade to postgres 9.5+ we should use upsert here
    oldb = db.get_db()
    json_data = entity.to_wikidata_api_json_format()

    if _get_from_cache(entity.id):
        return oldb.update(
            "wikidata",
            where="id=$id",
            vars={'id': entity.id},
            data=json_data,
            updated=entity._updated,
        )
    else:
        # We don't provide the updated column on insert because postgres defaults to the current time
        return oldb.insert("wikidata", id=entity.id, data=json_data)
