# Contributing

This page covers the community norms, contribution standards, and project management practices for Open Library. For setup and getting started, see the [Quick Start](https://docs.openlibrary.org/developers/quick-start.html) guide.

## Contributor Etiquette

We value all contributors and want to ensure a positive and collaborative environment. Please follow these guidelines:

### Respecting Other Contributors' Work

- **Do not undermine others' efforts**: If someone has already asked to work on an issue and been assigned (or is actively working on it), please respect their effort. Opening a competing PR without coordination undermines their contribution and violates our community spirit.
- **Check before starting**: Before beginning work on an issue, check if someone else is already assigned or has recently expressed interest in working on it.

### Requesting Issue Assignments

- **Quality over quantity**: Please do not ask to be assigned to dozens of issues at a time. Focus on making meaningful contributions rather than accumulating assignments.
- **Demonstrate understanding**: When requesting to be assigned to an issue, show that you understand the problem by including:
  - A summary of the challenge or bug
  - Your proposed approach to solving it
  - Which files or components you plan to modify
  - Any questions you have about the implementation
- **Use AI tools responsibly**: While you're encouraged to use AI tools (like LLMs) to assist with research and understanding the codebase, please don't simply copy-paste AI-generated responses into your comments. Take time to understand the suggestions and present them in your own words, demonstrating genuine comprehension of the issue.

## Submitting Pull Requests

1. **Test your code before opening a PR**: Maintainers may close your PR if it has clearly not been tested.
2. **Follow the pull request template**: It's easier for a maintainer to reject a PR than it is for them to fill it out for you.
3. **Make PRs _self-contained_**: They should clearly describe what changes have taken place. A reviewer should (for the most part) be able to complete a review without having to look at other issues.
4. **Resolve all code review (CR) comments**: Treat comments as a todo list. Most PRs will require some edits before getting merged, so don't get discouraged if you have to make some changes!
5. **Reply when resolving CR comments**: When resolving a comment, reply with "DONE" or "WON'T FIX because ...". A reviewer will unresolve a comment if they feel it's necessary.

## Managing Issues

### Picking Good First Issues

[Browse Good First Issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+label%3A%22Good+First+Issue%22+no%3Aassignee)

- Only pick issues that are **not assigned** to anyone
- If an issue has been assigned but has seen no response or activity for 2 weeks, you may comment to ask if you can take it
- Do not request to be assigned to issues that are actively being worked on
- If you have questions, ask the Lead designated by the `Lead: @person` label on the issue

### When No Good First Issues Are Available

If all Good First Issues are taken, here's how to find something to work on:

1. **Browse all unassigned issues** — [filter by recently updated](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+no%3Aassignee+sort%3Aupdated-desc) to find active discussions
2. **Look for older issues** that haven't had much activity. Before starting, verify the issue is still relevant by checking that the code area hasn't changed significantly, and leave a comment on the issue to confirm your intent
3. **Ask in Slack** — request an invite on our [volunteers page](https://openlibrary.org/volunteer). Maintainers can point you to what's actually useful right now
4. **Attend a weekly community call** — a good place to hear about current priorities
5. **Documentation improvements** are always welcome and don't require a full dev setup

### Tagging

- If an issue requires immediate fixing, include a comment requesting it be labeled and promoted as [`Priority: 0`](https://github.com/internetarchive/openlibrary/issues?q=is%3Aopen+is%3Aissue+label%3A%22Priority%3A+0%22).

## Code of Conduct

Please familiarize yourself with our [Code of Conduct](https://github.com/internetarchive/openlibrary/blob/master/CODE_OF_CONDUCT.md). We are a non-profit, open-source, inclusive project, and we believe everyone deserves a safe place to make the world a little better. We're committed to creating this safe place.

## Community

- The core Open Library team communicates over an invite-only Slack channel. Request an invitation on our [volunteers page](https://openlibrary.org/volunteer).
- We host weekly video calls. Check the [community call page](https://docs.openlibrary.org/everyone/community-call.html) for times and details.

## Roadmap

View this year's roadmap (and previous years') in the [Open Library Roadmap document](https://docs.google.com/document/d/1KJr3A81Gew7nfuyo9PnCLCjNBDs5c7iR4loOGm1Pafs/edit).
