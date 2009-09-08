#! /bin/bash

root=`dirname $0`

# run git submodule commands only when the working copy is a git repository 
# otherwise download tarballs of submodules
if [ -d $root/.git ];
then
    git submodule init
    git submodule update
else
    function get_tarball() {
        name=$1
        tag=$2
        wget http://github.com/$name/$name/tarball/$tag -O $name.tgz
        tar xvzf $name.tgz
        rm -rf $name
        mv $name-$name-* $name
    }
    get_tarball infogami master
fi

cd $root
./scripts/i18n-messages compile
