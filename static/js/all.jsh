#! /bin/bash
# script for generating static/build/all.js

DIR=`dirname $0`
OLROOT=$DIR/../..
JSROOT=$OLROOT/openlibrary/plugins/openlibrary/js
VENDORJS=$OLROOT/vendor/js

JSMIN="python $VENDORJS/wmd/jsmin.py"

for f in $JSROOT/*.js
do
    cat $f | $JSMIN
    echo
    echo
done
