#! /bin/bash

set -e

cd `dirname $0`/..
py.test                         \
    openlibrary/core            \
    openlibrary/plugins/books   \
    openlibrary/coverstore      \
    openlibrary/plugins/upstream \
    openlibrary/plugins/openlibrary

