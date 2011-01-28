#! /bin/bash

set -e

cd `dirname $0`/..
exec py.test                         \
    openlibrary/core            \
    openlibrary/mocks           \
    openlibrary/coverstore      \
    openlibrary/plugins/books   \
    openlibrary/plugins/upstream \
    openlibrary/plugins/openlibrary

