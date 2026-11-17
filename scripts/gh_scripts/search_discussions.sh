#!/usr/bin/env bash
# Search internetarchive/openlibrary GitHub Discussions for the issue enrichment bot.
#
# Usage: search_discussions.sh <keywords...>
#
# Prints one line per matching discussion, in every state (open, answered, closed),
# followed by the accepted answer when there is one. Read-only: the query is fixed
# and the keywords are passed as a GraphQL variable, so the caller cannot run
# arbitrary GraphQL (e.g. mutations) through this script.
#
# Always exits 0. If the token cannot read Discussions (missing permission, network
# error, rate limit), it prints a single "Discussions search unavailable" line so the
# caller can skip this source and carry on.

set -uo pipefail

repo="internetarchive/openlibrary"

# Keep the search inside this repo: drop any scope qualifiers from the keywords.
keywords=()
for word in "$@"; do
    case "$word" in
        repo:* | org:* | user:*) ;;
        *) keywords+=("$word") ;;
    esac
done

if [ ${#keywords[@]} -eq 0 ]; then
    echo "Usage: search_discussions.sh <keywords...>" >&2
    exit 0
fi

# No is:open / is:closed qualifier on purpose: closed and answered threads are
# often the most useful context.
search="repo:$repo ${keywords[*]}"

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

# shellcheck disable=SC2016 # $d etc. are jq variables, not shell ones
jq_filter='
.data.search as $s
| if $s.discussionCount == 0 then "No matching discussions."
  else
    $s.nodes[]
    | select(.number != null)
    | . as $d
    | ( if $d.closed then "closed: \($d.stateReason // "unknown" | ascii_downcase)"
        elif $d.isAnswered then "answered"
        else "open" end ) as $state
    | "#\($d.number) [\($state)] [\($d.category.name)] \($d.title) - \($d.url)"
      + ( if $d.answer.body then
            "\n    Accepted answer: " + ($d.answer.body | gsub("\\s+"; " ") | .[0:400])
          else "" end )
  end'

if ! output=$(gh api graphql -f query="$query" -f search="$search" --jq "$jq_filter" 2>&1); then
    # gh prints the raw error body before its own "gh: ..." summary; keep only the summary.
    reason=$(printf '%s\n' "$output" | grep -o 'gh: .*' | tail -n 1)
    echo "Discussions search unavailable (skip this source): ${reason:-$(printf '%s\n' "$output" | tail -n 1)}"
    exit 0
fi

echo "$output"
