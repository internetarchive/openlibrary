#!/usr/bin/env bash

cd /openlibrary
python setup.py build_ext --inplace

cd scripts/solr_builder
python setup.py build_ext --inplace
