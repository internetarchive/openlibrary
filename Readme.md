# Open Library

![Python Build](https://github.com/internetarchive/openlibrary/actions/workflows/python_tests.yml/badge.svg)
![JS Build](https://github.com/internetarchive/openlibrary/actions/workflows/javascript_tests.yml/badge.svg)
[![Join the chat at https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Open in Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)
[![contributors](https://img.shields.io/github/contributors/internetarchive/openlibrary.svg)](https://github.com/internetarchive/openlibrary/graphs/contributors)

[Open Library](https://openlibrary.org) is an open, editable library catalog, building towards a web page for every book ever published.

Are you looking to get started? [This is the guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) you are looking for. You may wish to learn more about [Google Summer of Code (GSoC)?](https://github.com/internetarchive/openlibrary/wiki/Google-Summer-of-Code) or [Hacktoberfest](https://github.com/internetarchive/openlibrary/wiki/Hacktoberfest).

## Table of Contents
   - [Overview](#overview)
   - [Installation](#installation)
   - [Code Organization](#code-organization)
   - [Architecture](#architecture)
     - [The Frontend](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide)
     - [The Backend](#the-backend)
     - [The Service Architecture](https://github.com/internetarchive/openlibrary/wiki/Production-Service-Architecture)
   - [Developer's Guide](#developers-guide)
   - [Running Tests](#running-tests)
   - [Contributing](#contributing)
   - [Public APIs](https://openlibrary.org/developers/api)
   - [FAQs](https://openlibrary.org/help/faq)

## Overview

Open Library is an effort started in 2006 to create "one web page for every book ever published." It provides access to many public domain and out-of-print books, which can be read online.

Here's a quick public tour of Open Library to get you familiar with the service and its offerings (10min).

[![archive org_embed_openlibrary-tour-2020 (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

- [Learn more about the Open Library project](https://openlibrary.org/about)
- [The Vision (Dream) of OpenLibrary](https://openlibrary.org/about/vision)
- [Visit the Blog](https://blog.openlibrary.org)

## Installation

Run `docker compose up` and visit http://localhost:8080

Need more details? Checkout the [Docker instructions](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md)
or [video tutorial](https://archive.org/embed/openlibrary-developer-docs/openlibrary-docker-set-up.mp4).

***Alternatively***, if you do not want to set up Open Library on your local computer, try Gitpod!
This lets you work on Open Library entirely in your browser without having to install anything on your personal computer.
Warning: This integration is still experimental.
[![Open In Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)

### Developer's Guide

For instructions on administrating your Open Library instance, refer to the Developer's [Quickstart](https://github.com/internetarchive/openlibrary/wiki/Getting-Started) Guide.

You can also find more information regarding Developer Documentation for Open Library in the Open Library [Wiki](https://github.com/internetarchive/openlibrary/wiki/).

## Code Organization

* openlibrary/core - core openlibrary functionality, imported and used by www
* openlibrary/plugins - other models, controllers, and view helpers
* openlibrary/views - views for rendering web pages
* openlibrary/templates - all the templates used in the website
* openlibrary/macros - macros are like templates, but can be called from wikitext

## Architecture

### The Backend

OpenLibrary is developed on top of the Infogami wiki system, which is itself built on top of the web.py Python web framework and the Infobase database framework.

- [Overview of Backend Web Technologies](https://openlibrary.org/about/tech)

Once you've read the overview of OpenLibrary Backend technologies, it's highly encouraged you read the developer primer which explains how to use Infogami (and its database, Infobase).

- [Infogami Developer Tutorial](https://openlibrary.org/dev/docs/infogami)

If you want to dive into the source code for Infogami, see the [Infogami repo](https://github.com/internetarchive/infogami).

## Running tests

Open Library tests can be run using docker. Kindly look up on our [Testing Document](https://github.com/internetarchive/openlibrary/wiki/Testing) for more details.

```
docker compose run --rm home make test
```

## Contributing

There are many ways volunteers can contribute to the Open Library project, from development and design to data management and community engagement. Here’s how you can get involved:

### Developers
- **Getting Started:** Check out our [Contributing Guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) for instructions on how to set up your development environment, find issues to work on, and submit your contributions.
- **Good First Issues:** Browse our [Good First Issues](https://github.com/internetarchive/openlibrary/issues?q=is%3Aissue+is%3Aopen+-linked%3Apr+label%3A%22Good+First+Issue%22+no%3Aassignee) to find beginner-friendly tasks.

### Designers
- **Design Contributions:** We welcome designers to help improve the user experience. You can start by looking at [design-related issues](https://github.com/internetarchive/openlibrary/labels/design).

### Librarians and Data Enthusiasts
- **Data Contributions:** Learn how to contribute to our catalog and help improve book data on Open Library. Visit our [volunteer page](https://openlibrary.org/volunteer) for more information.

### Community Engagement
- **Join our Community Calls:** Open Library hosts weekly community and design calls. Check the [community call schedule](https://github.com/internetarchive/openlibrary/wiki/Community-Call) for times and details.
- **Ask Questions:** If you have any questions, join our [gitter chat](https://gitter.im/theopenlibrary/Lobby) or request an invitation to our Slack channel on our [volunteers page](https://openlibrary.org/volunteer).

For more detailed information, refer to the [Contributing Guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md).


## License

All source code published here is available under the terms of the [GNU Affero General Public License, version 3](https://www.gnu.org/licenses/agpl-3.0.html).
