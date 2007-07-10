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

echo "** updating infogami repository **"

if [ -d $hgroot/infogami ]
then
   cd $hgroot/infogami && hg pull && hg update
else
    hg clone http://infogami.org/hg $hgroot/infogami
fi

