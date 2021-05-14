#!/bin/bash

# Util script to merge multiple branches as listed in a file into a new branch
# Used for dev.openlibrary.org "deploys"
# See make-integration-branch-sample.txt for a sample of the file format.

BRANCHES_FILE=$1
NEW_BRANCH=$2
ONLY_STARRED=$(grep '^\*\*' $BRANCHES_FILE | sed 's/\*\*//g' )

echo $ALL_BRANCHES
git checkout master
git pull origin master
git branch -D $NEW_BRANCH
git checkout -b $NEW_BRANCH

while read line; do
    branch=${line/\*\*/}
    if [[ -z $line || $line == "#"* ]] ; then
        :
    elif [[ ! -z $ONLY_STARRED && $line != "**"* ]] ; then
        :
    elif [[ $branch == "https://github.com/internetarchive/openlibrary/pull/"*".patch" ]] ; then
        echo -e "---\n$branch"
        curl -L $branch | git am -3
    elif [[ $branch == "https://"* ]] ; then
        echo -e "---\n$branch"
        git pull $branch
        # If the merge didn't succeed automatically, abort it
        [[ $(git ls-files -u) ]] && git merge --abort
    else
        echo -e "---\n$branch"
        git merge $branch
        # If the merge didn't succeed automatically, abort it
        [[ $(git ls-files -u) ]] && git merge --abort
    fi
done <"$BRANCHES_FILE"

echo "---"
echo "Complete; dev-merged created (SHA: $(git rev-parse --short HEAD))"
