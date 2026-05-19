#!/bin/bash

# Util script to merge multiple branches into a new integration branch.
# Used for dev.openlibrary.org "deploys".
#
# Usage:
#   ./make-integration-branch.sh <new-branch-name>
#     Build from _testing-prs.json (pinned commits).
#
#   ./make-integration-branch.sh <branches-file> <new-branch-name>
#     Add/update PRs from branches-file into _testing-prs.json (pinned to
#     their current fetched SHA), then build from the full state file.
#     This is how the bookmarklet path works: submitted PRs are added to
#     the list and pinned to commit, then the full list is built.
#     If no state file exists yet, one is created from the branches-file.

TESTING_STATE_FILE="_testing-prs.json"
NEW_BRANCH=${2:-$1}

# --- Phase 1: if a branches file was provided, add/update those PRs in the state ---
if [[ -n "$2" ]]; then
    BRANCHES_FILE=$1
    while IFS= read -r line; do
        # Match lines like "origin pull/123/head  # PR title"
        if [[ $line =~ ^origin\ pull/([0-9]+)/head ]]; then
            pr_num="${BASH_REMATCH[1]}"
            # Extract title after "# " if present, else fall back
            title="${line#*# }"
            [[ "$title" == "$line" ]] && title="PR #$pr_num"
            git fetch origin "pull/$pr_num/head"
            sha=$(git rev-parse FETCH_HEAD)
            python3 - "$pr_num" "$sha" "$title" <<'PYEOF'
import json, sys, datetime
pr_num, sha, title = int(sys.argv[1]), sys.argv[2], sys.argv[3]
state_file = '_testing-prs.json'
try:
    with open(state_file) as f:
        data = json.load(f)
except FileNotFoundError:
    data = {'last_deploy_at': '', 'prs': []}
# Handle old array format
if isinstance(data, list):
    data = {'last_deploy_at': '', 'prs': data}
prs = data['prs']
existing = next((p for p in prs if p['pr'] == pr_num), None)
if existing:
    existing['commit'] = sha  # bookmarklet = pull to latest
    existing.pop('pull_latest_sha', None)
else:
    prs.append({
        'pr': pr_num, 'commit': sha, 'active': True, 'title': title,
        'added_at': datetime.datetime.now(datetime.UTC).isoformat(), 'added_by': 'bookmarklet',
    })
with open(state_file, 'w') as f:
    json.dump(data, f, indent=2)
PYEOF
        fi
    done < "$BRANCHES_FILE"
fi

# --- Phase 2: build ---
git checkout master
git pull origin master
git branch -D "$NEW_BRANCH" 2>/dev/null || true
git checkout -b "$NEW_BRANCH"

if [[ -f "$TESTING_STATE_FILE" ]]; then
    # State file exists: merge pinned commits for all active PRs
    while IFS=' ' read -r pr_num pinned_sha; do
        echo -e "---\norigin pull/$pr_num/head  # pinned at $pinned_sha"
        git fetch origin "pull/$pr_num/head"
        # Ensure the pinned SHA is locally available
        if ! git cat-file -e "$pinned_sha^{commit}" 2>/dev/null; then
            git fetch origin "$pinned_sha" 2>/dev/null || true
        fi
        if ! git cat-file -e "$pinned_sha^{commit}" 2>/dev/null; then
            echo "Pinned commit $pinned_sha for PR #$pr_num unavailable — skipping"
            continue
        fi
        git merge "$pinned_sha"
        if [[ $(git ls-files -u) ]]; then
            git merge --abort
            echo "Merge conflict for PR #$pr_num (pinned $pinned_sha) — skipping"
        fi
    done < <(python3 -c "
import json
with open('$TESTING_STATE_FILE') as f:
    data = json.load(f)
prs = data['prs'] if isinstance(data, dict) else data
for p in prs:
    if p.get('active', True):
        print(p['pr'], p['commit'])
")
else
    # No state file and no branches file: nothing to build
    echo "Nothing to build: no state file and no branches file provided."
fi

echo "---"
echo "Complete; $NEW_BRANCH created (SHA: $(git rev-parse --short HEAD))"
