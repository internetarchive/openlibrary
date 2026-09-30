#!/bin/bash
# Fetch openlibrary-i18n at REF and install each locale's messages.po over the
# committed one, if it is safe to ship (see openlibrary.i18n.install_translations).
# A locale that fails keeps its committed file; pass --strict to exit 1 instead.
#
# docker/Dockerfile.olbase and the i18n_upstream CI job both run this, so CI checks
# exactly what olbase bakes. Run from the repository root.
#
# Usage: scripts/i18n-pull-translations.sh [REF] [--strict]
#   REF  branch, tag or commit SHA of openlibrary-i18n (default: main)
#   I18N_REPO env var overrides the repository URL (e.g. a local clone for testing)
#
# Writes openlibrary/i18n/openlibrary-i18n.txt: the ref, the resolved SHA, and
# whether each locale was installed or kept committed.
set -euo pipefail

REPO=${I18N_REPO:-https://github.com/internetarchive/openlibrary-i18n}
REF=main
if [[ $# -gt 0 && $1 != --* ]]; then
    REF=$1
    shift
fi
MANIFEST=openlibrary/i18n/openlibrary-i18n.txt

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git -C "$TMP" init -q
git -C "$TMP" fetch -q --depth=1 "$REPO" "$REF"
git -C "$TMP" checkout -q FETCH_HEAD
SHA=$(git -C "$TMP" rev-parse HEAD)
echo "openlibrary-i18n: $REF -> $SHA"

printf 'repository\t%s\nref\t%s\nsha\t%s\n' "$REPO" "$REF" "$SHA" > "$MANIFEST"
python ./scripts/i18n-messages install "$TMP/locale" --manifest "$MANIFEST" "$@"
