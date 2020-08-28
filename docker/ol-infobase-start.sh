#!/bin/bash

python --version

# su doesn't forward any environment variables, which kinda breaks pyenv
# So we include the variables pyenv needs here to forward
read -r -d '' PY_ENV_VARS << EOM
PATH="$PATH"
PYENV_VERSION="$PYENV_VERSION"
EOM

# infobase
su openlibrary -c "$PY_ENV_VARS && scripts/infobase-server conf/infobase.yml 7000"
