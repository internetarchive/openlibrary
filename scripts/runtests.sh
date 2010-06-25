#! /bin/bash

set -e

cd `dirname $0`/..
py.test                         \
    openlibrary/plugins/books   \
    openlibrary/coverstore

