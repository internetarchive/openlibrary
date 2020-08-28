#!/bin/bash

# quick method to start all ol services from one script
# inside an container, bypass all upstart/services

CONFIG=conf/openlibrary.yml

python --version

# su doesn't forward any environment variables, which kinda breaks pyenv
# So we include the variables pyenv needs here to forward
read -r -d '' PY_ENV_VARS << EOM
PATH="$PATH"
PYENV_VERSION="$PYENV_VERSION"
EOM

# ol server, running in the foreground to avoid exiting container
su openlibrary -c "$PY_ENV_VARS && authbind --deep scripts/openlibrary-server $CONFIG \
                     --gunicorn --reload --workers 4 --timeout 180 --bind :80"
