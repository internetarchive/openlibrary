# Getting Started

## Welcome!
This welcome section is intended for new contributors.

1. **Quick Tour:** [Quick Public Tour of Open Library (10min)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)
2. **Orientation:** [Volunteer Orientation Video (1.5h)](https://archive.org/details/openlibrary-orientation-2020?start=80)
    * [Code of conduct](https://github.com/internetarchive/openlibrary/blob/master/CODE_OF_CONDUCT.md)
3. **Getting Started:**
    * [Installation README](https://github.com/internetarchive/openlibrary/tree/master/docker) + [Docker Setup Walk-through (video)](https://archive.org/embed/openlibrary-developer-docs)
4. **Contributing:**
    * [How we use git](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet)
    * [Finding good first issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+label%3A%22Good+First+Issue%22+no%3Aassignee)
    * [Testing your code](https://github.com/internetarchive/openlibrary/wiki/Testing)
    * [Enabling debugging & profiling](https://github.com/internetarchive/openlibrary/wiki/Debugging-and-Performance-Profiling)
5. **Learning the Code:**
    * [Technical Tour & System Overview (1h)](https://archive.org/details/openlibrary-tour-2020/technical_overview.mp4)
    * [Walkthrough videos](https://archive.org/details/openlibrary-tour-2020)
    * [Code Architecture](https://github.com/internetarchive/openlibrary#architecture)
    * [Front-end Guide](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide)
    * [Open Library Public APIs](https://openlibrary.org/developers/api)
6. **Common Tasks**
    * [Logging in locally](https://github.com/internetarchive/openlibrary/wiki/Getting-Started#logging-in)
    * [Importing Production Book Data Locally](https://github.com/internetarchive/openlibrary/wiki/Loading-Production-Book-Data)  
7. **Questions?**
    * [Wiki](https://github.com/internetarchive/openlibrary/wiki)
    * [Request a slack invite](https://openlibrary.org/volunteer)
    * [Weekly Community calls](https://github.com/internetarchive/openlibrary/wiki/Community-Call)
    * [Open Library FAQs](https://openlibrary.org/help/faq)
## Quick Tour

A quick public tour of Open Library to get you familiar with the service and its offerings (10min)

[![archive org_embed_openlibrary-tour-2020_openlibrary ogv (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

## Onboarding

A comprehensive volunteer orientation video to learn what it means to work on Open Library (1.5h). This video is a companion to our [Orientation Guide](https://docs.google.com/document/d/1fkTDqYFx2asuMWwSIDQRHJlnu-AGWpMrDDd9o5z8Cik/edit#).
If you're looking for a good first issue, check out [Good First Issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+label%3A%22Good+First+Issue%22+no%3Aassignee).

[![archive org_details_openlibrary-orientation-2020_start=80](https://user-images.githubusercontent.com/978325/91350387-78272580-e79b-11ea-9e26-85cfd1d38fe1.png)](https://archive.org/details/openlibrary-orientation-2020?start=80)

## Technical Walkthrough

A deep dive into the technical details, architecture, and code structure behind OpenLibrary.org

[![archive org_details_openlibrary-tour-2020_technical_overview mp4](https://user-images.githubusercontent.com/978325/91350097-11097100-e79b-11ea-87bd-ca9724d5e43c.png)](https://archive.org/details/openlibrary-tour-2020/technical_overview.mp4)

### Code of Conduct

Before continuing, please familiarize yourself with our [code of conduct](https://github.com/internetarchive/openlibrary/blob/master/CODE_OF_CONDUCT.md).
We are a non-profit, open-source, inclusive project, and we believe everyone deserves a safe place to make the world a little better. We're committed to creating this safe place.

### Join our Community

* The core Open Library team communicates over an invite-only Slack channel. You may request an invitation on our [volunteers](https://openlibrary.org/volunteer) page.
* If you have a quick question about getting started, anyone can ask on our [gitter chat](https://gitter.im/theopenlibrary/Lobby).
* The Open Library hosts two weekly video calls:
    * The Open Library general Community Call every Tuesday @ 9:00am PT
    * The Open Library Design call on Friday @ 9:00am PT
    * [Request an invite](https://openlibrary.org/volunteer) to join us!

## Installing Open Library
For instructions on setting up a local developer's instance of Open Library, please refer to the [Installation Guide](https://github.com/internetarchive/openlibrary#installation).

[![archive org_details_openlibrary-developer-docs_zoom_0 mp4_autoplay=1 start=2](https://user-images.githubusercontent.com/978325/91351305-ef10ee00-e79c-11ea-9bfb-c2733696ec58.png)](https://archive.org/details/openlibrary-developer-docs/zoom_0.mp4)


Also, refer to the [Quickstart Guide](https://github.com/internetarchive/openlibrary/wiki/Getting-Started).
[Here's a handy cheat sheet](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet) if you are new to using Git.

## Common Setup Tasks

### Logging in as Admin
Our login process on Open Library's dev instance is a bit funky. You need to correctly enter the right credentials (email: `openlibrary@example.com` pw: `admin123`) the **first** time or you will be logged in with a non-admin account (and will not be able to login as admin until you clear your cookies). More info here:
- https://github.com/internetarchive/openlibrary/issues/1197#issuecomment-479752932

### Adding Data to Open Library
- If you are looking to add data using MARC and ONIX records, visit [Open Library Bots](https://github.com/internetarchive/openlibrary-bots).

## Submitting Issues

[Interacting with GitHub Issues](https://github.com/internetarchive/openlibrary/wiki/Interacting-with-GitHub-Issues) and [Using Managed Labels to Track Issues](https://github.com/internetarchive/openlibrary/wiki/Using-Managed-Labels-to-Track-Issues) explain how GitHub issues are triaged, labeled, and prioritized.

### Data Cleanup
- If you notice a set of entries on Open Library which need to be updated (possibly in bulk) please report them as an issue to https://github.com/internetarchive/openlibrary-client (the Open Library Client).

### Tagging
- If an issue requires immediate fixing, please include a comment requesting for it to be labeled and promoted as [`Priority: 0`](https://github.com/internetarchive/openlibrary/issues?q=is%3Aopen+is%3Aissue+label%3A%22Priority%3A+0%22+).

## Picking Good First Issues

[Here's a list of good first issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+label%3A%22Good+First+Issue%22+no%3Aassignee) to help you get started. Please only pick issues that are not assigned to anyone, or if an issue has been assigned but has seen no response or activity for 2 weeks. Do not request to be assigned to issues that are actively being worked on. If you're interested in working on an issue without an assignee or one that has been inactive, comment on it to ask if you can be assigned.  If you have questions, please ask the [Lead](https://github.com/internetarchive/openlibrary/wiki/Using-Managed-Labels-to-Track-Issues#triage) designated by the `Lead: @person` label on the issue.

### Our Roadmap(s)
You can see this year (and previous year's) roadmap(s) [here](https://docs.google.com/document/d/1KJr3A81Gew7nfuyo9PnCLCjNBDs5c7iR4loOGm1Pafs/edit).

## Development Practices

Whenever working on a new feature/hotfix/refactor, make sure a corresponding issue exists.
We use the issue number in the branch name.

A branch name consists of the: issue number, whether it is a feature/hotfix/refactor, and a human readable slug, e.g:

```
123/refactor/simplifying-authentication-using-xauthn
```

With respect to client side patches, before submitting your patch you'll want to check it adheres to code styling rules and tests. We use `npm` to test our client side code.

```
npm install --no-audit
npm test
```

If it passes your patch is ready for review!

Many issues can be automatically fixed using the following command:

```
npm run lint-fix
```

## pre-commit hooks

Be confident in changing files you can check the quality (linter) with [pre-commit](https://pre-commit.com/index.html).
It is used to inspect the snapshot that is about to be committed, to see if there are any syntax errors, typos, or a handful of other common issues.
You can see the actions descriptions in [pre-commit-config.yml](https://github.com/internetarchive/openlibrary/blob/master/.pre-commit-config.yaml).

The pre-commit is automatically run against open PRs. Install the pre-commit locally to avoid waiting for the PR checks to run in the cloud.

### Installation

```
pip install pre-commit
# or on mac you can run
brew install pre-commit
```

After executing the last command, when you normally run `git commit`, pre-commit will also perform its checks.

### Running manually

```
pre-commit run --files pre-commit-config.yml
```

> **_Warning:_**  If you don't clone with **ssh** then infogami will have pre-commit issues [You can read this section to resolve it](docker/README.md#cloning-the-open-library-repository).


### Submitting Pull Requests

Once you've finished making your changes, submit a pull request (PR). Please take the time to check whether someone has already raised the issue you are solving. Thank you for your contributions!

Follow these rules when creating a PR:

1. **Test your code before opening a PR**: Maintainers may close your PR if it has clearly not been tested.
2. **Follow the pull request template**: It's easier for a maintainer to reject a PR than it is for them to fill it out for you.
3. **Make PRs _self-contained_**: They should clearly describe what changes have taken place. A reviewer should (for the most part) be able to complete a review without having to look at other issues.
4. **Resolve all code review (CR) comments**: Treat comments as a todo list. Most PRs will require some edits before getting merged, so don't get discouraged if you have to make some changes!
5. **Reply when resolving CR comments**: When resolving a comment, reply with either "DONE" or "WON'T FIX because ...". A reviewer will unresolve a comment if they feel it's necessary.

## QA Testing

Once a Pull Request has been submitted, ask an approved member of staff to spin up an isolated kubernetes Open Library pod for the branch that you're working on.
They will give you a link which will let you test your branch's current code against a near-production environment.
Read more about our [Plans for Kubernetes](https://github.com/internetarchive/openlibrary/wiki/Kubernetes)

# Maintainers

Guidelines for repo maintainers.

## Pull Requests

We use assignee to denote PR ownership. If you are the assignee, then you should have the PR on your todo list until you merge or close it.
- **Assign yourself** to a PR if you have the time to take on the responsibilities of ownership (described below).
- **Don't assign others** to a PR. Feel free to ask someone to take ownership, but respect others' time restrictions.
- **Avoid assignee=author**. In the case where the PR author is also a maintainer, we will strive to have another maintainer own and merge the PR to ensure these steps are followed fairly by all.

The assignee of a PR is responsible for:
- **being the primary contact** for the PR author. Be polite; you're the face of the community to this contributor.
- **managing the PR's labels**. Add `Needs: Author Input` or `Needs: Review` as necessary.
- **ensuring the PR doesn't get stuck**. Avoid leaving the author wondering about the state of the PR. If you don't have time right now, saying "I'm a little swamped now but will try to get to this in \_" is better than radio silence for a week.
- **getting the PR code reviewed** either by yourself (often so) or by someone else.
- **getting merge approval**. If a PR requires a special deploy, label as `Needs: Deploy Approval` and get that approval before merging.
- **testing the PR** before merging. Comment about how you tested in the PR. If _any_ changes are made to the PR code, you will have to test it again before merging.
- **merging (or closing)** the PR.

Each Monday (as of 2022) we triage PRs (excluding drafts) and make sure they have leads assigneed so that nothing gets stuck.
