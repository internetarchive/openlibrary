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
    # Use production infogami
    make git
  fi
fi

reindex-solr() {
  server=$1
  config=$2
  for thing in books authors; do
    psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep "^/$thing/" \
      | PYTHONPATH=$PWD xargs python openlibrary/solr/update_work.py -s $server -c $config --data-provider=legacy
  done
}

echo "Starting ol services."

# TODO: why does nginx appear not necessary?
#echo "Starting nginx"
#service nginx restart

# su doesn't forward any environment variables, which kinda breaks pyenv
# So we include the variables pyenv needs here to forward
read -r -d '' PY_ENV_VARS << EOM
PATH="$PATH"
PYENV_VERSION="$PYENV_VERSION"
EOM

export -f reindex-solr
su openlibrary -c "$PY_ENV_VARS && until pg_isready --host db; do sleep 5; done && reindex-solr localhost $CONFIG" &

# solr updater
su solrupdater -c "$PY_ENV_VARS && python scripts/new-solr-updater.py \
  -c $CONFIG \
  --state-file solr-update.offset \
  --ol-url http://web/" &

# ol server, running in the foreground to avoid exiting container
su openlibrary -c "$PY_ENV_VARS && authbind --deep scripts/openlibrary-server $CONFIG \
                     --gunicorn --reload --workers 4 --timeout 180 --bind :80"
