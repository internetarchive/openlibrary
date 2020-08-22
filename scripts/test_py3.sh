#!/bin/sh

pytest . \
       --ignore=openlibrary/plugins/openlibrary/tests/test_home.py \
       --ignore=openlibrary/records/tests \
       --ignore=tests/integration \
       --ignore=scripts/2011 \
       --ignore=infogami \
       --ignore=vendor
RETURN_CODE=$?

pytest --show-capture=all -v openlibrary/plugins/openlibrary/tests/test_home.py || true  # internetarchive/openlibrary#3670
flake8 --exit-zero --count --select=E722 --show-source  # Show all the bare exceptions
safety check || true  # Show any insecure dependencies

exit ${RETURN_CODE}
