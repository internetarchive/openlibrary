# Getting Started

## Installing Open Library
For instructions on setting up a local developer's instance of Open Library, please refer to the [Installation Guide](https://github.com/internetarchive/openlibrary#installation). Also, refer to the [Quickstart Guide](https://github.com/internetarchive/openlibrary/wiki/Getting-Started).

## Resources for Contributors

Look through our issues related to [`contributing`](https://github.com/internetarchive/openlibrary/issues?utf8=%E2%9C%93&q=is%3Aissue+is%3Aopen+label%3Acontributing).

## Want to Participate in the Community?
- Ask here to join our Open Library slack: https://github.com/internetarchive/openlibrary/issues/686
- Join us for our Open Library Community Call every Tuesday @ 11:30am PT

## Submitting Issues

### Data Cleanup
- If you notice a set of entries on Open Library which need to be updated (possibly in bulk) please report them as an issue to https://github.com/internetarchive/openlibrary-client (the Open Library Client).

### Adding Data to Open Library
- In case you are looking to add data using MARC and ONIX records, possibly in bulk please do it via at https://github.com/internetarchive/openlibrary-bots (the Open Library Bots).

### Tagging
- If a task requires immediate fixing, please respond to its corresponding issue by asking if it can be promoted to [`blocker`](https://github.com/internetarchive/openlibrary/issues?q=is%3Aopen+is%3Aissue+label%3Ablocker) using the blocker issue label.

## Picking Tasks
We usually discuss weekly goals via our Tuesday Community Call and using slack.

### Picking 1st task
- Look for issues with labels such as [`good first issue`](https://github.com/internetarchive/openlibrary/issues?q=is%3Aopen+is%3Aissue+label%3A%22good+first+issue%22) and [`easy`](https://github.com/internetarchive/openlibrary/issues?utf8=%E2%9C%93&q=is%3Aopen+is%3Aissue+label%3Aeasy)

### Our Roadmap(s)
- Our on-going tasks are tracked here: https://github.com/internetarchive/openlibrary/projects/1
- Our quarterly goals can be found on the projects board: https://github.com/internetarchive/openlibrary/projects

## Development

Whenever working on a new feature/hotfix/refactor, the first step is to make sure a corresponding issue exists. We then take this issue number and affix it to the branch name which we will use for development.

A branch name consists of the: issue number, whether it is a feature/hotfix/refactor, and a human readable slug, e.g:

```
123/refactor/simplifying-authentication-using-xauthn
```

## Pull Requests

* Pull Requests (PRs) should link to the issue they resolve. Please take the time to check whether someone has already raised the issue you are solving. At the very least PRs should contain enough detail in the description to explain the purpose of the PR; what feature it adds, or problem it solves. Please expect PRs without sufficient details to be rejected until an clear description of the benefit is added. Thank you for your contributions!

* When your code is ready for review, please follow our [Pull Request Template](https://github.com/internetarchive/openlibrary/blob/master/PULL_REQUEST_TEMPLATE.md) to close the corresponding Issue.
