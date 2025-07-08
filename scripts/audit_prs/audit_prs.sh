#!/bin/bash

# Configuration
REPO="internetarchive/openlibrary"
YEAR="2023"

get_merged_prs() {
    gh pr list --state merged --search "created:${YEAR}-01-01..${YEAR}-12-31" --limit "2000" --json number -q '.[].number'
}

# https://api.github.com/repos/internetarchive/openlibrary/pulls/10941/comments?per_page=100

get_pr_comments() {
    local pr_id="$1"
    local json_file="data/pr-comments/${YEAR}/$pr_id.json"
    mkdir -p "$(dirname "$json_file")"

    if [ ! -f "$json_file" ]; then
        echo "Fetching comments for PR #$pr_id from GitHub API..."
        gh api repos/${REPO}/pulls/"$pr_id"/comments > "$json_file"
    fi

    cat "$json_file"
}

get_merged_prs | while read -r pr_id; do
    get_pr_comments "$pr_id"
done

# The jq looks a little complicated but it's mostly just grabbing a few fields, putting everything in an array, and filtering for empty ones
cat data/pr-comments/${YEAR}/*.json | jq -s '[.[] | select(length > 0) | {pr_id: .[0].pull_request_url | tostring | split("/")[7], comments: [.[] | {diff_hunk: .diff_hunk, user: .user.login, body: .body}]}]' > data/pr-comments/${YEAR}-comments.json
