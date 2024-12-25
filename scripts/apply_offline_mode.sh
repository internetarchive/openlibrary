#!/bin/bash
#####
# This script applies the changes from the `offline-mode` branch in the `internetarchive/openlibrary` repo.
# These changes will mock or otherwise prevent API calls to Internet Archive, resulting in a better
# developer experience when IA is down.
#####

reverse=''

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --reverse)
            reverse='--reverse'
            shift
            ;;
        *)
            # Handle other arguments or show usage
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

curl "https://github.com/internetarchive/openlibrary/compare/master...offline-mode.patch" | git apply $reverse
