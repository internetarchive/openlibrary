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
        user=$1
        project=$2
        tag=$3
        wget http://github.com/$user/$project/tarball/$tag -O $project.tgz
        tar xvzf $project.tgz
        rm -rf $project
        mv $user-$project-* $project
    }
    get_tarball infogami infogami master
    get_tarball internetarchive acs4_py master
fi

cd $root
./scripts/i18n-messages compile
