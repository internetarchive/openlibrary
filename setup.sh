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

    if [ -d $hgroot/infogami.new ]
    then
       cd $hgroot/infogami.new && hg pull
    else
        cd $hgroot && hg clone http://infogami.org/src/infogami.new $hgroot/infogami.new
    fi
    cd $hgroot/infogami.new && hg update -C default
}

function setup_webpy() {
    if [ ! -d $hgroot/webpy ]
    then
        echo "** fetching web.py**"

        cd $hgroot && wget http://webpy.org/static/web.py-0.23.tar.gz
        cd $hgroot && tar xzf web.py-0.23.tar.gz
    fi
}

function setup_symlinks() {
    echo "**creating symlinks**"
    cd $hgroot/pharos
    ln -fs ../infogami.new/infogami .
    ln -fs ../webpy/web .
}

setup_infogami
setup_webpy
setup_symlinks
