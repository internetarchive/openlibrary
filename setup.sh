#! /bin/bash

root=`dirname $0`

# run git submodule commands only when the working copy is a git repository 
# (do nothing when the source is downloaded from a tarball/zipball).
if [ -d $root/.git ];
then
    git submodule init
    git submodule update
fi
