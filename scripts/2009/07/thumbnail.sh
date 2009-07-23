#!/bin/bash

function files() {
    for i in `seq 0 32`
    do
        printf "$1/$1_%02d.warc " $i
    done
}


exec python thumbnail.py tars `files $1`
