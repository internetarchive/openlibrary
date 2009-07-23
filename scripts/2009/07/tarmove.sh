#! /bin/bash
# move tar files from multiple places to current dir
# If a file with same name exists in multiple dirs, then combine those tar files

ROOT=$PWD

for d in $*
do
    # convert d to absolute path
    # if d does not start with /
    if [ "${d#/}" = "$d" ]; then
        d="$PWD/$d"
    fi
    
    for f in $d/*.tar
    do
        echo $f
        name=`basename $f`
        if [ -e "$name" ]; then
            echo "*** merging $name"
            cd /tmp/retar
            rm -rf *
            tar xf $ROOT/$name
            tar xf $f
            rm $ROOT/$name
            tar cf $ROOT/$name *
            rm *
            cd $ROOT
        else
            ln -s $f $ROOT
        fi
    done
done