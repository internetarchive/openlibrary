# Status Page GitHub Fetch

The `/status` testing panel makes one GitHub GraphQL POST for all tracked PRs on a memcache miss. The existing 60-second `status.github_pr_drift` cache behavior is unchanged.

Each aliased `pullRequest(number: N)` selects `title`, `headRefOid`, `author { login avatarUrl }`, `assignees { login avatarUrl }`, `state`, `mergedAt`, and `isDraft`; these replace the REST PR fields one-for-one. `commits(last: 100)` supplies the pinned-SHA drift calculation; when the pin is unavailable in that history, drift remains unknown (`-1`).

GitHub GraphQL requires `github_api_token`. A null PR node becomes `PRNotFoundError`; transport, GraphQL, and malformed-response failures become `GitHubUnavailableError`.
