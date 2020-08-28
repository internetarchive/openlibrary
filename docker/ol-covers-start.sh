#!/bin/bash

CONFIG=conf/coverstore.yml

python --version

# su doesn't forward any environment variables, which kinda breaks pyenv
# So we include the variables pyenv needs here to forward
read -r -d '' PY_ENV_VARS << EOM
PATH="$PATH"
PYENV_VERSION="$PYENV_VERSION"
EOM

su openlibrary -c "$PY_ENV_VARS && scripts/coverstore-server $CONFIG \
    --gunicorn --workers 1 --max-requests 250 --bind :8081"
