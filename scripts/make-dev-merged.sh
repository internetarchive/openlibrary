#!/bin/bash

# Util script to merge multiple branches as listed in a file into a new branch
# Used for dev.openlibrary.org deploys

NEW_BRANCH=dev-merged
BRANCHES_FILE=$1

git checkout master
git pull origin master
git branch -D $NEW_BRANCH
git checkout -b $NEW_BRANCH

while read branch; do
    if [[ $branch == "#"* ]] ; then
        :
    elif [[ $branch == "https://"* ]] ; then
        git pull $branch
    else
        git merge $branch
    fi
done <"$BRANCHES_FILE"
