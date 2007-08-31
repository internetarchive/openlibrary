#!/bin/sh -e

. ./config.sh

exec python2.5 "$PHAROS_REPO/catalog/marc/show-marc.py"

