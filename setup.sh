#! /bin/bash

root=`dirname $0`

# update submodules
git submodule sync
git submodule init
git submodule update

cd $root
./scripts/i18n-messages compile
