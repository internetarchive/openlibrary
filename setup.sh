#! /bin/bash

function base() {
    set $* $PWD
    root=$1
    if [ -d $1/.hg ]
    then 
        echo $1
    else
        base `dirname $1`
    fi
}

hgroot=`base`

function setup_infogami() {
    echo "** updating infogami repository **"

    if [ -d $hgroot/infogami ]
    then
       cd $hgroot/infogami && hg pull
    else
        cd $hgroot && hg clone http://infogami.org/hg $hgroot/infogami
    fi
    cd $hgroot && hg update -C ol_softlaunch
}

function setup_webpy() {
    echo "** updating webpy repository **"

    if [ -d $hgroot/web ]
    then
       cd $hgroot/web && svn up -q
    else
        cd $hgroot && svn co -q http://webpy.org/svn/trunk/web
    fi
}

function setup_symlinks() {
    echo "**creating symlinks**"
    cd $hgroot/pharos
    ln -fs ../infogami/infogami .
    ln -fs ../web .
}

setup_infogami
setup_webpy
setup_symlinks
