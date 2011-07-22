#! /bin/bash

root=`dirname $0`

# udpate submodules
git submodule sync
git submodule init
git submodule update

cd $root
./scripts/i18n-messages compile
