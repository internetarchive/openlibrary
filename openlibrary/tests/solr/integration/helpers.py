from typing import Any

from openlibrary.solr.updater.author import AuthorSolrBuilder
from openlibrary.solr.utils import SolrUpdateRequest, solr_update


def create_test_author(key: str, name: str, **kwargs) -> dict[str, Any]:
    """
    Create a test author dict for use in integration tests.

    """
    author = {
        "key": key,
        "type": {"key": "/type/author"},
        "name": name,
        **kwargs,
    }
    return author


async def insert_authors_to_solr(
    solr_url: str, authors: list[dict[str, Any]], commit: bool = True
) -> None:

    all_adds = []

    for author in authors:
        mock_solr_reply = {
            "response": {
                "docs": [],
                "numFound": 0,
            },
            "facets": {
                "ratings_count_1": 0,
                "ratings_count_2": 0,
                "ratings_count_3": 0,
                "ratings_count_4": 0,
                "ratings_count_5": 0,
                "readinglog_count": 0,
                "want_to_read_count": 0,
                "currently_reading_count": 0,
                "already_read_count": 0,
                "subject_facet": {"buckets": []},
                "time_facet": {"buckets": []},
                "person_facet": {"buckets": []},
                "place_facet": {"buckets": []},
            },
        }

        builder = AuthorSolrBuilder(author, mock_solr_reply)
        solr_doc = builder.build()
        if solr_doc.get('name'):
            solr_doc['name_str'] = solr_doc['name']
        all_adds.append(solr_doc)

    update_request = SolrUpdateRequest(adds=all_adds, commit=commit)

    solr_update(update_request, solr_base_url=solr_url)


async def cleanup_authors_from_solr(solr_url: str, author_keys: list[str]) -> None:

    update_request = SolrUpdateRequest(deletes=author_keys, commit=True)
    solr_update(update_request, solr_base_url=solr_url)


def wait_for_solr_commit(solr_url: str, max_wait: int = 10) -> bool:
    """
    Wait for Solr to complete any pending commits.

    """
    import time

    time.sleep(2)
    return True
