#!/bin/bash

# Clone or update docs wiki so developers and AI assistants can search
# documentation locally without switching to the browser.
if [ -d "/openlibrary/docs/wiki/.git" ]; then
    echo "Updating docs wiki..."
    cd /openlibrary/docs/wiki && git pull --ff-only
elif [ -d "/openlibrary/docs/wiki" ]; then
    echo "docs/wiki exists but is not a git repo, skipping..."
else
    echo "Cloning docs wiki..."
    git clone https://github.com/internetarchive/openlibrary.wiki.git /openlibrary/docs/wiki
fi
cd /openlibrary

make reindex-solr
