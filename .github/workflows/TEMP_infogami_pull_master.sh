#!/bin/bash

if [ -z "$CI" ]
then
    echo "Only runs under continuous integration"
    exit 1
fi

pushd /openlibrary/vendor/infogami
git pull origin master
popd
