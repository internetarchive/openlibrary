# Getting Started

## Welcome!
This welcome section is intended for new contributors.

### Quick Tour

A quick public tour of Open Library to get your familiar with the service and its offerings (10min)

[![archive org_embed_openlibrary-tour-2020_openlibrary ogv (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

### Onboarding

A comprehensive volunteer orientation video to learn what it means to work on Open Library (1.5h). This video is a companion to our [Orientation Guide](https://docs.google.com/document/d/1fkTDqYFx2asuMWwSIDQRHJlnu-AGWpMrDDd9o5z8Cik/edit#). If you're looking for a good first issue, check out [Menu of Opportunities](https://docs.google.com/document/d/1CgWXIsyn_kTZ_6n3n_zfSDuglj1yLUjVtg1EjL0Bf6E/edit#heading=h.gzsl3sqg0r51).

[![archive org_details_openlibrary-orientation-2020_start=80](https://user-images.githubusercontent.com/978325/91350387-78272580-e79b-11ea-9e26-85cfd1d38fe1.png)](https://archive.org/details/openlibrary-orientation-2020?start=80)

### Technical Walkthrough

A deep dive into the technical details, architecture, and code structure behind OpenLibrary.org

[![archive org_details_openlibrary-tour-2020_technical_overview mp4](https://user-images.githubusercontent.com/978325/91350097-11097100-e79b-11ea-87bd-ca9724d5e43c.png)](https://archive.org/details/openlibrary-tour-2020/technical_overview.mp4)

### Code of Conduct

Before continuing, please familiarize yourself with our [code of conduct](https://github.com/internetarchive/openlibrary/blob/master/CODE_OF_CONDUCT.md). We are a non-profit, open-source, inclusive project, and we believe everyone deserves a safe place to make the world a little better. We're committed to creating this safe place:

https://github.com/internetarchive/openlibrary/blob/master/CODE_OF_CONDUCT.md

### Join our Community

* The core Open Library team communicates over an invite-only slack channel. You may request an invitation on our [volunteers](https://openlibrary.org/volunteer) page. 
* If you have a quick question about getting started, anyone can ask on our [gitter chat](https://gitter.im/theopenlibrary/Lobby).
* The Open Library hosts a video Community Call every Tuesday @ 10:00am PT, [request an invite](https://openlibrary.org/volunteer) to join us!

Resources for Contributors

Look through our issues related to [`contributing`](https://github.com/internetarchive/openlibrary/issues?utf8=%E2%9C%93&q=is%3Aissue+is%3Aopen+label%3Acontributing).


## Installing Open Library
For instructions on setting up a local developer's instance of Open Library, please refer to the [Installation Guide](https://github.com/internetarchive/openlibrary#installation). 

[![archive org_details_openlibrary-developer-docs_zoom_0 mp4_autoplay=1 start=2](https://user-images.githubusercontent.com/978325/91351305-ef10ee00-e79c-11ea-9bfb-c2733696ec58.png)](https://archive.org/details/openlibrary-developer-docs/zoom_0.mp4)


Also, refer to the [Quickstart Guide](https://github.com/internetarchive/openlibrary/wiki/Getting-Started). [Here's a handy cheat sheet](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet) if you are new to using Git.

## Common Setup Tasks

### Logging in as Admin
Our login process on Open Library's dev instance is a bit funky. You need to correctly enter the right credentials (email: `openlibrary@example.com` pw: `admin123`) the **first** time or you will be logged in with a non-admin account (and will not be able to login as admin until you clear your cookies). More info here:
- https://github.com/internetarchive/openlibrary/issues/1197#issuecomment-479752932

### Adding Data to Open Library
- In case you are looking to add data using MARC and ONIX records, possibly in bulk please do it via at https://github.com/internetarchive/openlibrary-bots (the Open Library Bots).

## Submitting Issues

[Interacting with GitHub Issues](https://github.com/internetarchive/openlibrary/wiki/Interacting-with-GitHub-Issues) and [Using Managed Labels to Track Issues](https://github.com/internetarchive/openlibrary/wiki/Using-Managed-Labels-to-Track-Issues) explain how GitHub issues are triaged, labeled, and prioritized.

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
npm run lint-fix
```

## Submitting Pull Requests

Once you've finished making your changes, submit a pull request (PR) to get your code into Open Library. Please take the time to check whether someone has already raised the issue you are solving. Thank you for your contributions!

Follow these rules when creating a PR:

1. **Follow the pull request template**: It's easier for a maintainer to reject a PR than it is for them to fill it out for you.
2. **Make PRs _self-contained_**: They should clearly describe what changes have taken place. A reviewer should (for the most part) be able to complete a review without having to look at other issues.
3. **Resolve all code review (CR) comments**: Treat comments as a todo list. Most PRs will require some edits before getting merged, so don't get discouraged if you have to make some changes!
4. **Reply when resolving CR comments**: When resolving a comment, reply with either "DONE" or "WON'T FIX because ...". A reviewer will unresolve a comment if they feel it's necessary.

## QA Testing

Once a Pull Request has been submitted, ask an approved member of staff to spin up an isolated kubernetes Open Library pod for the branch that you're working on. They will give you a link which will let you test your branch's current code against a near-production environment. Read more about our [Plans for Kubernetes](https://github.com/internetarchive/openlibrary/wiki/Kubernetes)

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
