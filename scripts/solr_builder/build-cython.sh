#!/usr/bin/env bash

cd /openlibrary

# Clean up any previously cythonized files
find openlibrary -name "*.so" -delete
find openlibrary -name "*.c" -delete
find scripts/solr_builder -name "*.so" -delete
find scripts/solr_builder -name "*.c" -delete

# Then rebuild
python setup.py build_ext --inplace
python scripts/solr_builder/setup.py build_ext --inplace
