# Getting Started

## Installing Open Library
For instructions on setting up a local developer's instance of Open Library, please refer to the [Installation Guide](https://github.com/internetarchive/openlibrary#installation). Also, refer to the [Quickstart Guide](https://github.com/internetarchive/openlibrary/wiki/Getting-Started).

## Resources for Contributors

Look through our issues related to [`contributing`](https://github.com/internetarchive/openlibrary/issues?utf8=%E2%9C%93&q=is%3Aissue+is%3Aopen+label%3Acontributing).

## Want to Participate in the Community?
- Ask here to join our Open Library slack: https://github.com/internetarchive/openlibrary/issues/686
- Join us for our Open Library Community Call every Tuesday @ 11:30am PT

## Common Setup Tasks

### Logging in as Admin
Our login process on Open Library's dev instance is a bit funky. You need to correctly enter the right credentials (email: `openlibrary@example.com` pw: `admin123`) the **first** time or you will be logged in with a non-admin account (and will not be able to login as admin until you clear your cookies). More info here:
- https://github.com/internetarchive/openlibrary/issues/1197#issuecomment-479752932

### Adding Data to Open Library
- In case you are looking to add data using MARC and ONIX records, possibly in bulk please do it via at https://github.com/internetarchive/openlibrary-bots (the Open Library Bots).

## Submitting Issues

### Data Cleanup
- If you notice a set of entries on Open Library which need to be updated (possibly in bulk) please report them as an issue to https://github.com/internetarchive/openlibrary-client (the Open Library Client).

### Tagging
- If a task requires immediate fixing, please respond to its corresponding issue by asking if it can be promoted to [`blocker`](https://github.com/internetarchive/openlibrary/issues?q=is%3Aopen+is%3Aissue+label%3Ablocker) using the blocker issue label.

## Picking Tasks
We usually discuss weekly goals via our Tuesday Community Call and using slack.

### Picking 1st task
- Look for issues with labels such as [`good first issue`](https://github.com/internetarchive/openlibrary/issues?q=is%3Aopen+is%3Aissue+label%3A%22good+first+issue%22) and [`easy`](https://github.com/internetarchive/openlibrary/issues?utf8=%E2%9C%93&q=is%3Aopen+is%3Aissue+label%3Aeasy)

### Our Roadmap(s)
- Our quarterly goals can be found on the corresponding projects board: https://github.com/internetarchive/openlibrary/projects

## Development Practices

Whenever working on a new feature/hotfix/refactor, the first step is to make sure a corresponding issue exists. We then take this issue number and affix it to the branch name which we will use for development.

A branch name consists of the: issue number, whether it is a feature/hotfix/refactor, and a human readable slug, e.g:

```
123/refactor/simplifying-authentication-using-xauthn
```

With respect to client side patches, before submitting your patch you'll want to check it adheres to code styling rules and tests. We use `npm` to test our client side code.

```
npm install
npm test
```

If it passes your patch is ready for review!

Note, many issues can be fixed automatically without any manual work from your part using the following command:

```
npm run lint:fix
```

## Submitting Pull Requests

Once you've finished making your changes, submit a pull request (PR) to get your code into Open Library. Please take the time to check whether someone has already raised the issue you are solving. Thank you for your contributions!

Follow these rules when creating a PR:

1. **Follow the pull request template**: It's easier for a maintainer to reject a PR than it is for them to fill it out for you.
2. **Make PRs _self-contained_**: They should clearly describe what changes have taken place. A reviewer should (for the most part) be able to complete a review without having to look at other issues.
3. **Resolve all code review (CR) comments**: Treat comments as a todo list. Most PRs will require some edits before getting merged, so don't get discouraged if you have to make some changes!
4. **Reply when resolving CR comments**: When resolving a comment, reply with either "DONE" or "WON'T FIX because ...". A reviewer will unresolve a comment if they feel it's necessary.

## QA Testing

Once a Pull Request has been subitted, ask an approved member of staff to spin up an isolated kubernetes Open Library pod for the branch that you're working on. They will give you a link which will let you test your branch's current code against a near-production environment. Read more about our [Plans for Kubernetes](https://github.com/internetarchive/openlibrary/wiki/Kubernetes)

# Maintainers

Guidelines for repo maintainers.

## Pull Requests

We use assignee to denote PR ownership. If you are the assignee, then you should have the PR on your todo list until you merge or close it.
- **Assign yourself** to a PR if you have the time to take on the responsibilities of ownership (described below).
- **Don't assign others** to a PR. Feel free to ask someone to take ownership, but respect others time restrictions.
- **Avoid assignee=author**. In the case where the PR author is also a maintainer, we will strive to have another maintainer own and merge the PR to ensure these steps are followed fairly by all.

The assignee of a PR is responsible for:
- **being the primary contact** for the PR author. Be polite; you're the face of the community to this contributor.
- **managing the PR's labels**. Add `Needs: Author Input` or `Needs: Review` as necessary.
- **ensuring the PR doesn't get stuck**. Avoid leaving the author wondering about the state of the PR. If you don't have time right now, saying "I'm a little swamped now but will try to get to this in \_" is better than radio silence for a week.
- **getting the PR code reviewed** either by yourself (often so) or by someone else.
- **getting merge approval**. If a PR requires a special deploy, label as `Needs: Deploy Approval` and get that approval before merging.
- **testing the PR** before merging. Comment about how you tested in the PR. If _any_ changes are made to the PR code, you will have to test it again before merging.
- **merging (or closing)** the PR.

We strive for every PR to have an assignee so that nothing gets stuck.