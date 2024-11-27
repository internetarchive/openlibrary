"""
The purpose of this file is to:
1. Interact with the Wikidata API
2. Store the results
3. Make the results easy to access from other files
"""

import web
import requests
import logging
from dataclasses import dataclass
from openlibrary.core import db
from openlibrary.core.helpers import days_since

from datetime import datetime
import json
import re

logger = logging.getLogger("core.wikidata")

WIKIDATA_API_URL = 'https://www.wikidata.org/w/rest.php/wikibase/v0/entities/items/'
WIKIDATA_CACHE_TTL_DAYS = 30

# TODO: Pull the icon, label, and base_url from wikidata itself
SOCIAL_PROFILE_CONFIGS = [
    {
        "icon_name": "google_scholar.svg",
        "wikidata_property": "P1960",
        "label": "Google Scholar",
        "base_url": "https://scholar.google.com/citations?user=",
    }
]

# The keys in this dict need to match their corresponding names in openlibrary/plugins/openlibrary/config/author/identifiers.yml
# Ordered by what I assume is most (viaf) to least (amazon/youtube) reliable for author matching
REMOTE_IDS = {
    "viaf": "P214",
    "isni": "P213",
    "lc_naf": "P244",
    "opac_sbn": "P396",
    "project_gutenberg": "P1938",
    "librivox": "P1899",
    "bookbrainz": "P2607",
    "musicbrainz": "P434",
    "librarything": "P7400",
    "goodreads": "P2963",
    "storygraph": "P12430",
    "imdb": "P345",
    "amazon": "P4862",
    "youtube": "P2397",
}


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

    def get_description(self, language: str = 'en') -> str | None:
        """If a description isn't available in the requested language default to English"""
        return self.descriptions.get(language) or self.descriptions.get('en')

    def get_external_profiles(self, language: str = 'en') -> list[dict]:
        """
        Get formatted social profile data for all configured social profiles.

        Returns:
            List of dicts containing url, icon_url, and label for all social profiles
        """
        profiles = []
        profiles.extend(self._get_wiki_profiles(language))

        for profile_config in SOCIAL_PROFILE_CONFIGS:
            values = self._get_statement_values(profile_config["wikidata_property"])
            profiles.extend(
                [
                    {
                        "url": f"{profile_config['base_url']}{value}",
                        "icon_url": f"/static/images/identifier_icons/{profile_config["icon_name"]}",
                        "label": profile_config["label"],
                    }
                    for value in values
                ]
            )
        return profiles

    def get_remote_ids(self) -> dict[str, any]:
        """
        Get remote IDs like viaf, isni, etc.

        Returns:
            Dict containing identifier names as keys and lists of corresponding values
        """
        remote_ids = {}

        for service, id in REMOTE_IDS.items():
            values = self._get_statement_values(id)
            remote_ids[service] = values
        return remote_ids

    def get_openlibrary_id(self) -> str | None:
        """
        Get open library ID of WD item. Mostly used to validate connection between WD item and OL thing

        Returns:
            OL ID, if it exists
        """
        res = self._get_statement_values("P648")
        if len(res) > 0:
            return res[0]
        return None

    def _get_wiki_profiles(self, language: str) -> list[dict]:
        """
        Get formatted Wikipedia and Wikidata profile data for rendering.

        Args:
            language: The preferred language code (e.g., 'en')

        Returns:
            List of dicts containing url, icon_url, and label for Wikipedia and Wikidata profiles
        """
        profiles = []

        # Add Wikipedia link if available
        if wiki_link := self._get_wikipedia_link(language):
            url, lang = wiki_link
            label = "Wikipedia" if lang == language else f"Wikipedia (in {lang})"
            profiles.append(
                {
                    "url": url,
                    "icon_url": "/static/images/identifier_icons/wikipedia.svg",
                    "label": label,
                }
            )

        # Add Wikidata link
        profiles.append(
            {
                "url": f"https://www.wikidata.org/wiki/{self.id}",
                "icon_url": "/static/images/identifier_icons/wikidata.svg",
                "label": "Wikidata",
            }
        )

        return profiles

    def _get_wikipedia_link(self, language: str = 'en') -> tuple[str, str] | None:
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

    def _get_statement_values(self, property_id: str) -> list[str]:
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

    # can this move into author def'n?
    def consolidate_remote_author_ids(self) -> None:
        output = {"wikidata": self.id}
        ol_id = self.get_openlibrary_id()
        if ol_id is None or not re.fullmatch(r"^OL\d+A$", ol_id):
            return

        key = "/authors/" + ol_id
        q = {"type": "/type/author", "key~": key}
        reply = list(web.ctx.site.things(q))
        authors = [web.ctx.site.get(k) for k in reply]
        if len(authors) != 1:
            return output
        author = authors[0]
        if author.wikidata() is not None and author.wikidata().id != self.id:
            raise Exception("wikidata IDs do not match")
        wd_remote_ids = {
            key: value[0] for key, value in self.get_remote_ids().items() if value != []
        }

        # Verify that the author's IDs are not significantly different.
        output, _ = author.merge_remote_ids(wd_remote_ids)

        # save
        author.remote_ids = output
        web.ctx.site.save(query={**author, "key": key, "type": {"key": "/type/author"}})


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
    ol_id = entity.get_openlibrary_id()

    # here, we should write WD data to author remote ids
    if re.fullmatch(r"^OL\d+A$", ol_id):
        try:
            entity.consolidate_remote_author_ids()
        except:
            # don't error out if we can't save WD ids to remote IDs. might be a case of identifiers not matching what we have in OL
            # TODO: raise a flag to librarians here?
            pass

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
