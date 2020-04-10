#!/bin/sh

pytest openlibrary/mocks openlibrary/olbase openlibrary/utils scripts/tests \
    openlibrary/catalog/add_book/tests/test_add_book.py \
    openlibrary/catalog/add_book/tests/test_load_book.py \
    openlibrary/catalog/add_book/tests/test_match.py \
    openlibrary/catalog/marc/tests/test_marc_binary.py \
    openlibrary/catalog/marc/tests/test_marc_html.py \
    openlibrary/catalog/merge/test_amazon.py \
    openlibrary/catalog/merge/test_merge.py \
    openlibrary/catalog/merge/test_merge_marc.py \
    openlibrary/catalog/merge/test_names.py \
    openlibrary/catalog/merge/test_normalize.py \
    openlibrary/coverstore/tests/test_code.py \
    openlibrary/coverstore/tests/test_webapp.py \
    openlibrary/plugins/admin/tests/test_services.py \
    openlibrary/plugins/books/tests/test_doctests.py \
    openlibrary/plugins/books/tests/test_dynlinks.py \
    openlibrary/plugins/importapi/tests/test_code_ils.py \
    openlibrary/plugins/importapi/tests/test_import_edition_builder.py \
    openlibrary/plugins/openlibrary/tests/test_borrow_home.py \
    openlibrary/plugins/openlibrary/tests/test_lists.py \
    openlibrary/plugins/openlibrary/tests/test_stats.py \
    openlibrary/plugins/upstream/tests/test_account.py \
    openlibrary/plugins/upstream/tests/test_addbook.py \
    openlibrary/plugins/upstream/tests/test_forms.py \
    openlibrary/plugins/upstream/tests/test_merge_authors.py \
    openlibrary/plugins/upstream/tests/test_related_carousels.py \
    openlibrary/plugins/upstream/tests/test_utils.py \
    openlibrary/plugins/worksearch/tests/test_worksearch.py \
    openlibrary/tests/accounts/test_models.py \
    openlibrary/tests/core/test_cache.py \
    openlibrary/tests/core/test_connections.py \
    openlibrary/tests/core/test_helpers.py \
    openlibrary/tests/core/test_i18n.py \
    openlibrary/tests/core/test_ia.py \
    openlibrary/tests/core/test_init.py \
    openlibrary/tests/core/test_lending.py \
    openlibrary/tests/core/test_lists_engine.py \
    openlibrary/tests/core/test_models.py \
    openlibrary/tests/core/test_olmarkdown.py \
    openlibrary/tests/core/test_processors.py \
    openlibrary/tests/core/test_processors_invalidation.py \
    openlibrary/tests/core/test_ratings.py \
    openlibrary/tests/core/test_sponsors.py \
    openlibrary/tests/core/test_vendors.py \
    openlibrary/tests/core/test_waitinglist.py \
    openlibrary/tests/solr/test_update_work.py
RETURN_CODE=$?

# The following sections allow us to quickly spot tests that are fixed

# catalog: All failing tests run in allow failures (|| true) mode
pytest \
    openlibrary/catalog/marc/tests/test_get_subjects.py \
    openlibrary/catalog/marc/tests/test_marc.py \
    openlibrary/catalog/marc/tests/test_parse.py \
    openlibrary/tests/catalog/test_get_ia.py \
    || true

# coverstore: All failing tests run in allow failures (|| true) mode
pytest \
    openlibrary/coverstore/tests/test_coverstore.py \
    openlibrary/coverstore/tests/test_doctests.py \
    || true

# plugins: All failing tests run in allow failures (|| true) mode
pytest openlibrary/plugins/openlibrary/tests/test_home.py || true

exit ${RETURN_CODE}
