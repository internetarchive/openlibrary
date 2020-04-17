#!/bin/sh

pytest openlibrary/catalog openlibrary/coverstore openlibrary/mocks openlibrary/olbase \
       openlibrary/plugins openlibrary/tests openlibrary/utils scripts/tests \
       --ignore=openlibrary/catalog/marc/tests/test_get_subjects.py \
       --ignore=openlibrary/catalog/marc/tests/test_parse.py \
       --ignore=openlibrary/tests/catalog/test_get_ia.py \
       --ignore=openlibrary/coverstore/tests/test_doctests.py \
       --ignore=openlibrary/plugins/openlibrary/tests/test_home.py
RETURN_CODE=$?
       
pytest openlibrary/catalog/marc/tests/test_get_subjects.py || true
pytest openlibrary/catalog/marc/tests/test_parse.py || true
pytest openlibrary/tests/catalog/test_get_ia.py || true
pytest --show-capture=all openlibrary/coverstore/tests/test_doctests.py || true
pytest --show-capture=all openlibrary/plugins/openlibrary/tests/test_home.py || true

exit ${RETURN_CODE}
