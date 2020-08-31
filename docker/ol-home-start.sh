#!/bin/bash

# quick method to start all ol services from one script
# inside an container, bypass all upstart/services

CONFIG=conf/openlibrary.yml

python --version

if [[ "$INFOGAMI" = "local" ]]; then
  # If we're using the local copy of infogami, don't pull anything
  # and just use what's there
  echo "Using local infogami"
else
  if [[ "$PYENV_VERSION" = 3* || -n $INFOGAMI ]]; then
    pushd vendor/infogami
    # Use Python 3 compatible infogami
    git pull origin "${INFOGAMI:-master}"
    popd
  else
    # Use same version of infogami that's used on production
    make git
  fi
fi

until pg_isready --host db; do sleep 5; done
make reindex-solr

# solr updater
python scripts/new-solr-updater.py \
  -c $CONFIG \
  --state-file solr-update.offset \
  --ol-url http://web/
