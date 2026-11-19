#!/usr/bin/env bash
# Read-only Discussions search for the issue enrichment bot. Always exits 0; prints "Discussions search unavailable" if the token can't read Discussions.

set -uo pipefail

query='
query($search: String!) {
  search(type: DISCUSSION, query: $search, first: 10) {
    discussionCount
    nodes {
      ... on Discussion {
        number
        title
        url
        closed
        stateReason
        isAnswered
        category { name }
        answer { body }
      }
    }
  }
}'

jq_filter='
.data.search as $s
| if $s.discussionCount == 0 then "No matching discussions."
  else
    $s.nodes[]
    | . as $d
    | ( if $d.closed then "closed: \($d.stateReason // "unknown" | ascii_downcase)"
        elif $d.isAnswered then "answered"
        else "open" end ) as $state
    | "#\($d.number) [\($state)] [\($d.category.name)] \($d.title) - \($d.url)"
      + ( if $d.answer.body then
            "\n    Accepted answer: " + ($d.answer.body | gsub("\\s+"; " ") | .[0:400])
          else "" end )
  end'

if ! output=$(gh api graphql -f query="$query" -f search="repo:internetarchive/openlibrary $*" --jq "$jq_filter" 2>&1); then
    echo "Discussions search unavailable (skip this source): $(printf '%s\n' "$output" | grep -o 'gh: .*' | tail -n 1)"
    exit 0
fi

echo "$output"
