#!/bin/sh

pytest . \
       --ignore=tests/integration \
       --ignore=scripts/2011 \
       --ignore=infogami \
       --ignore=vendor
RETURN_CODE=$?

flake8 --exit-zero --count --select=E722,F403 --show-source --statistics  # Show bare exceptions and wildcard (*) imports
safety check || true  # Show any insecure dependencies

exit ${RETURN_CODE}
