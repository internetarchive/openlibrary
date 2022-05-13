#!/usr/bin/env bash

OL_USER=openlibrary

pg_dump --host=db -U $OL_USER openlibrary
