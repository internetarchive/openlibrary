#!/bin/sh

set -e

# Where is conftest.py?
# zsh: ls **/*.py | grep conftest
# openlibrary/catalog/add_book/tests/conftest.py
# openlibrary/conftest.py
# openlibrary/plugins/admin/tests/conftest.py
# openlibrary/plugins/openlibrary/tests/conftest.py
# openlibrary/records/tests/was_conftest.py
# openlibrary/tests/core/conftest.py
# vendor/infogami/infogami/conftest.py

pytest --doctest-modules \
        --ignore=infogami \
        --ignore=openlibrary/catalog/amazon/add_covers.py \
        --ignore=openlibrary/catalog/amazon/amazon_to_arc.py \
        --ignore=openlibrary/catalog/amazon/arc_index.py \
        --ignore=openlibrary/catalog/amazon/crawl_top_books.py \
        --ignore=openlibrary/catalog/amazon/extract_amazon_fields.py \
        --ignore=openlibrary/catalog/amazon/import.py \
        --ignore=openlibrary/catalog/amazon/list_done.py \
        --ignore=openlibrary/catalog/amazon/load_merge.py \
        --ignore=openlibrary/catalog/marc/lang.py \
        --ignore=openlibrary/catalog/marc/read_toc.py \
        --ignore=openlibrary/catalog/marc/show_records.py \
        --ignore=openlibrary/catalog/marc/tests/test_get_subjects.py \
        --ignore=openlibrary/catalog/marc/tests/test_parse.py \
        --ignore=openlibrary/catalog/add_book/tests \
        --ignore=openlibrary/catalog/merge/build_db.py \
        --ignore=openlibrary/catalog/merge/load_from_json.py \
        --ignore=openlibrary/core/ia.py \
        --ignore=openlibrary/plugins/akismet/code.py \
        --ignore=openlibrary/plugins/importapi/metaxml_to_json.py \
        --ignore=openlibrary/plugins/openlibrary/dev_instance.py \
        --ignore=openlibrary/plugins/openlibrary/tests/test_home.py \
        --ignore=openlibrary/plugins/search/code.py \
        --ignore=openlibrary/plugins/search/collapse.py \
        --ignore=openlibrary/plugins/search/solr_client.py \
        --ignore=openlibrary/plugins/upstream/addbook.py \
        --ignore=openlibrary/plugins/upstream/jsdef.py \
        --ignore=openlibrary/plugins/upstream/utils.py \
        --ignore=openlibrary/records/tests/test_functions.py \
        --ignore=openlibrary/solr/db_load_authors.py \
        --ignore=openlibrary/solr/db_load_works.py \
        --ignore=openlibrary/solr/read_dump.py \
        --ignore=openlibrary/solr/update_work.py \
        --ignore=openlibrary/tests/catalog/test_get_ia.py \
        --ignore=openlibrary/utils/form.py \
        --ignore=openlibrary/utils/schema.py \
        --ignore=openlibrary/utils/solr.py \
        --ignore=scripts \
        --ignore=tests \
        --ignore=vendor \
        .
