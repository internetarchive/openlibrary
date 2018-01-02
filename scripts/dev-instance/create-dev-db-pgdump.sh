#!/usr/bin/env bash

OL_USER=vagrant

pg_dump -U $OL_USER openlibrary
