#!/bin/bash

source config.sh

string="3:foo,"
result=`echo -n $string | ${PHAROS_PERL?} marc8_to_utf8.pl`

if [ "x$result" == "x$string" ]; then
	echo "ok"
	exit 0
else
	echo "bad result: $result"
	exit 1
fi
