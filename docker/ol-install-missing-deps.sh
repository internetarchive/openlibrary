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
