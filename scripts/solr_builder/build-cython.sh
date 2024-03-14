#!/usr/bin/env bash

cd /openlibrary
python setup.py build_ext --inplace
python scripts/solr_builder/setup.py build_ext --inplace
