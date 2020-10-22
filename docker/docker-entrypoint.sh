#!/bin/bash
set -e

# Init PYENV vars
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

exec "$@"
