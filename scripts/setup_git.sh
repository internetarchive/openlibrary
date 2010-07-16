#!/bin/bash

# Add "upstream" remote with read/write access
git remote add upstream git@github.com:openlibrary/openlibrary.git

# Fetch upstream so we know about its branches
git fetch upstream

# Add local tracking branches
git branch --track olmaster upstream/master
git branch --track olproduction upstream/production
