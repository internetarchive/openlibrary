#!/bin/bash
#
# Helper: install Python deps that may have been added/updated since the
# Docker image was built.  This lets developers pull a branch that adds a
# new dependency (e.g. to requirements.txt) and run `docker compose up`
# without needing an explicit `docker compose build` first.
#
# Usage: add `source docker/ol-install-missing-deps.sh` to a startup script
# after `python --version` but before the main process is launched.
#
# TODO: Update this to use uv instead of pip as part of #13034
# (https://github.com/internetarchive/openlibrary/pull/13034).  The uv
# binary is available in the image, but the openlibrary user can't write
# to system site-packages, so the install must go to a user-writeable
# location. Until uv's --user flag is confirmed, pip --user is the safe
# choice.
#
# Remove this file once the associated PR branch is merged and the new
# image has been published.

python -c "import pydantic_settings" 2>/dev/null || python -m pip install -q --user 'pydantic-settings==2.9.1'
