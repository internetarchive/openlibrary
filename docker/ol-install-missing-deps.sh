#!/bin/bash
#
# Temporary workaround: ensure .venv is on PATH and deps are synced.
#
# The Docker images are stale — they don't have /openlibrary/.venv/bin on
# PATH and may be missing recently-added dependencies.  Once the images
# are rebuilt (after this PR merges), this file can be removed and the
# `source` lines deleted from all startup scripts.
#
# Usage: add `source docker/ol-install-missing-deps.sh` to a startup script
# after `python --version` but before the main process is launched.

if [ "${LOCAL_DEV:-false}" = "true" ]; then
  export PATH="/openlibrary/.venv/bin:${PATH}"
  uv sync --frozen --no-install-project --extra test
fi
# Don't rely on the host shell having sourced build_env.sh before `docker
# compose up` — /olsystem is already bind-mounted into the container, so
# pick up PIP_INDEX_URL directly from there if it wasn't already set.
if [ -z "${PIP_INDEX_URL:-}" ] && [ -f /olsystem/bin/build_env.sh ]; then
  source /olsystem/bin/build_env.sh
fi

python -c "import pydantic_settings" 2>/dev/null || python -m pip install -q --user --index-url "${PIP_INDEX_URL:-https://pypi.org/simple/}" 'pydantic-settings==2.9.1'
