import pytest

from openlibrary.plugins.worksearch.code import run_solr_query
from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme
from openlibrary.tests.solr.integration.helpers import (
    cleanup_authors_from_solr,
    create_test_author,
    insert_authors_to_solr,
    wait_for_solr_commit,
)


@pytest.mark.skip(
    reason=("Failing test - documents incorrect behavior of name sort option. ")
)
@pytest.mark.asyncio
async def test_author_search_sort_by_name(solr_container):
    """
    Test that author search with sort='name' returns results in correct alphabetical order.

    """
    from openlibrary.solr.utils import set_solr_base_url

    set_solr_base_url(solr_container)

    authors = [
        create_test_author("/authors/OL1A", "Tavernier, Alice"),
        create_test_author("/authors/OL2A", "Tavernier, Bob"),
        create_test_author("/authors/OL3A", "Tavernier, John"),
    ]

    try:
        await insert_authors_to_solr(solr_container, authors, commit=True)

        wait_for_solr_commit(solr_container)

        response = run_solr_query(
            AuthorSearchScheme(),
            {"q": "Tavernier"},
            sort="name",
            rows=10,
        )

        result_names = [doc.get("name") for doc in response.docs if doc.get("name")]

        expected_order = ["Tavernier, Alice", "Tavernier, Bob", "Tavernier, John"]

        assert (
            result_names == expected_order
        ), f"Expected {expected_order}, got {result_names}"

    finally:
        author_keys = [author["key"] for author in authors]
        await cleanup_authors_from_solr(solr_container, author_keys)
