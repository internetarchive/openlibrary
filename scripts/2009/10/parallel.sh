#! /bin/bash

n=$1
shift

for i in `seq $n`
do
    $* &
done
wait
