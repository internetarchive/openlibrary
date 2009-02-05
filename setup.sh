#! /bin/bash

function base() {
    set $* $PWD
    root=$1
    if [ -d $1/.git ]
    then 
        echo $1
    else
        base `dirname $1`
    fi
}

gitroot=`base`

function setup_infogami() {
    echo "** updating infogami repository **"

    if [ -d $gitroot/infogami ]
    then
       cd $gitroot/infogami && git pull
    else
        cd $gitroot && git clone git://github.com/infogami/infogami $gitroot/infogami
    fi
}

function setup_webpy() {
    if [ ! -d $gitroot/webpy ]
    then
        echo "** fetching web.py**"

        cd $gitroot && wget http://webpy.org/static/web.py-0.31.tar.gz
        cd $gitroot && tar xzf web.py-0.31.tar.gz
    fi
}

function setup_symlinks() {
    echo "**creating symlinks**"
    cd $gitroot/pharos
    ln -fs ../infogami/infogami .
    ln -fs ../webpy/web .
}

setup_infogami
setup_webpy
setup_symlinks
