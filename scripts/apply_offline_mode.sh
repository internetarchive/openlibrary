#!/bin/bash
#####
# This script applies the changes from the `offline-mode` branch in the `internetarchive/openlibrary` repo.
# These changes will mock or otherwise prevent API calls to Internet Archive, resulting in a better
# developer experience when IA is down.
#####

touch offline.patch
curl "https://github.com/internetarchive/openlibrary/compare/master...offline-mode.patch" -o offline.patch
git apply offline.patch
rm offline.patch
