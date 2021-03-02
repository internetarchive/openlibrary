#!/bin/bash

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

FILES_WITH_DOCTESTS=$(grep -l -r -F '>>>' --include=\*.py openlibrary | sort)
FILES_TO_EXCLUDE=$(sort <<EOF
openlibrary/catalog/amazon/add_covers.py
openlibrary/catalog/amazon/amazon_to_arc.py
openlibrary/catalog/amazon/arc_index.py
openlibrary/catalog/amazon/crawl_top_books.py
openlibrary/catalog/amazon/extract_amazon_fields.py
openlibrary/catalog/amazon/import.py
openlibrary/catalog/amazon/list_done.py
openlibrary/catalog/amazon/load_merge.py
openlibrary/catalog/amazon/read_serp.py
openlibrary/catalog/edition_merge/find_dups.py
openlibrary/catalog/edition_merge/find_easy.py
openlibrary/catalog/edition_merge/merge.py
openlibrary/catalog/edition_merge/merge_works.py
openlibrary/catalog/edition_merge/run_merge.py
openlibrary/catalog/marc/lang.py
openlibrary/catalog/marc/read_toc.py
openlibrary/catalog/marc/show_records.py
openlibrary/catalog/marc/tests/test_get_subjects.py
openlibrary/catalog/marc/tests/test_parse.py
openlibrary/catalog/add_book/tests
openlibrary/catalog/merge/build_db.py
openlibrary/catalog/merge/load_from_json.py
openlibrary/core/ia.py
openlibrary/plugins/akismet/code.py
openlibrary/plugins/importapi/metaxml_to_json.py
openlibrary/plugins/openlibrary/dev_instance.py
openlibrary/plugins/openlibrary/tests/test_home.py
openlibrary/plugins/search/code.py
openlibrary/plugins/search/collapse.py
openlibrary/plugins/search/solr_client.py
openlibrary/plugins/upstream/addbook.py
openlibrary/plugins/upstream/jsdef.py
openlibrary/plugins/upstream/utils.py
openlibrary/records/tests/test_functions.py
openlibrary/solr/db_load_authors.py
openlibrary/solr/db_load_works.py
openlibrary/solr/read_dump.py
openlibrary/solr/update_work.py
openlibrary/tests/catalog/test_get_ia.py
openlibrary/tests/solr/test_update_work.py
openlibrary/utils/form.py
openlibrary/utils/schema.py
openlibrary/utils/solr.py
EOF
)
FILES_TO_TEST=$(join -v 1 <(echo $FILES_WITH_DOCTESTS | tr " " "\n") <(echo $FILES_TO_EXCLUDE | tr " " "\n"))
pytest --doctest-modules $(for f in $FILES_TO_EXCLUDE; do echo " --ignore=$f "; done) $FILES_TO_TEST
