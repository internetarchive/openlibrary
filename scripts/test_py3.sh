#!/bin/sh

pytest . \
       --ignore=scripts/2011 \
       --ignore=infogami \
       --ignore=vendor
RETURN_CODE=$?

ruff --exit-zero --select=E722,F403 --show-source  # Show bare exceptions and wildcard (*) imports
safety check || true  # Show any insecure dependencies

exit ${RETURN_CODE}
