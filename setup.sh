#! /bin/bash

git submodule init
git submodule update

root=`dirname $0`

cd $root/pharos
ln -fs ../infogami/infogami .
ln -fs ../webpy/web .

