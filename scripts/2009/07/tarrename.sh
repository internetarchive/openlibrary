#! /bin/bash

for f in $*
do
    f2=`echo $f | sed 's/\(covers_[0-9]*_[0-9]*\)[-_]\([SML]\).tar/\2_\1.tar/' | tr 'A-Z' 'a-z'`
    echo mv $f $f2
done