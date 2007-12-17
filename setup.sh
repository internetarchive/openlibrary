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

function version_compare() {
    python -c "f = lambda s: map(int, s.split('.')); print cmp(f('$1'), f('$2'))"
}

function get_hg_version() {
    hg --version | head -1 | sed 's/[^0-9.]//g'
}

function ensure_hg_version() {
    v1="0.9.4"
    v2=`get_hg_version`
    cmp=`version_compare $v1 $v2`
    if [ $cmp -gt 0 ]
    then
        echo "Require hg version >= $v1" 1>&2
        exit 1
    fi
}

function setup_infogami() {
    echo "** updating infogami repository **"

    ensure_hg_version

    if [ -d $hgroot/infogami ]
    then
       cd $hgroot/infogami && hg pull
    else
        cd $hgroot && hg clone http://infogami.org/hg/ $hgroot/infogami
    fi
    cd $hgroot/infogami && hg update -C default
}

function setup_webpy() {
    echo "** updating webpy repository **"

    if [ -d $hgroot/webpy ]
    then
       cd $hgroot/webpy && bzr pull
    else
        cd $hgroot && bzr get http://webpy.org/bzr/webpy-0.23 webpy
    fi
}

function setup_symlinks() {
    echo "**creating symlinks**"
    cd $hgroot/pharos
    ln -fs ../infogami/infogami .
    ln -fs ../webpy/web .
}

setup_infogami
setup_webpy
setup_symlinks
