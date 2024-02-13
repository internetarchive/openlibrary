# Open Library

![Python Build](https://github.com/internetarchive/openlibrary/actions/workflows/python_tests.yml/badge.svg)
![JS Build](https://github.com/internetarchive/openlibrary/actions/workflows/javascript_tests.yml/badge.svg)
[![Join the chat at https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Open in Gitpod](https://img.shields.io/badge/Contribute%20with-Gitpod-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)

[Open Library](https://openlibrary.org) aims to create a web page for every book ever published, offering an open and editable catalog that enriches public access to a vast collection of books. This initiative includes a wide range of titles, from rare and out-of-print editions to contemporary works, all available for online reading. Through this platform, readers around the globe can freely explore, read, and contribute to preserving and sharing the wealth of knowledge contained in books.

Are you looking to get started? [This is the guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) you are looking for. You may wish to learn more about [Google Summer of Code (GSoC)?](https://github.com/internetarchive/openlibrary/wiki/Google-Summer-of-Code) or [Hacktoberfest](https://github.com/internetarchive/openlibrary/wiki/Hacktoberfest).

## Table of Contents
   - [Overview](#overview)
   - [How to Use Open Library](#how-to-use-open-library)
   - [Installation](#installation)
   - [Code Organization](#code-organization)
   - [Architecture](#architecture)
     - [The Frontend](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide)
     - [The Backend](#the-backend)
     - [The Service Architecture](https://github.com/internetarchive/openlibrary/wiki/Production-Service-Architecture)
   - [Developer's Guide](#developers-guide)
   - [Running Tests](#running-tests)
   - [Contributing](CONTRIBUTING.md)
   - [Public APIs](https://openlibrary.org/developers/api)
   - [FAQs](https://openlibrary.org/help/faq)
   - [Badges](#badges)

## Overview

Open Library is an effort started in 2006 to create "one web page for every book ever published." It provides access to many public domain and out-of-print books, which can be read online.

Here's a quick public tour of Open Library to get you familiar with the service and its offerings (10 minutes).

[![archive org_embed_openlibrary-tour-2020 (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

- [Learn more about the Open Library project](https://openlibrary.org/about)
- [The Vision (Dream) of OpenLibrary](https://openlibrary.org/about/vision)
- [Visit the Blog](https://blog.openlibrary.org)

## How to Use Open Library

The Open Library offers an intuitive interface for users to explore and read a vast collection of books online. To get started, follow these simple steps:

1. **Searching for Books**: Use the search bar at the top of the Open Library homepage to find books by title, author, ISBN, or subjects.
2. **Reading Online**: Once you've found a book of interest, click on the book's title to view its details page. Here, if the book is available for online reading, you'll see a "Read" button. Click it to start reading the book in your browser.
3. **Borrowing Books**: For books available to borrow, you'll see a "Borrow" option. This requires a free Open Library account, which you can create through the website.
4. **Exploring Collections**: Explore curated collections or browse by subjects to discover new titles.

For a more comprehensive guide on using the Open Library, including advanced features like creating lists, contributing, and more, visit our [Help Center](https://openlibrary.org/help).

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

Open Library tests can be run using pytest. Kindly look up on our [Testing Document](https://github.com/internetarchive/openlibrary/wiki/Testing) for more details.

Run tests while the docker container is running.

```
cd docker/
docker compose exec web make test
```

### Integration Tests

Integration tests use the Splinter webdriver with Google Chrome. For instructions on installation requirements and running integration tests, [see Integration Tests README](tests/integration/README.md).

## License

All source code published here is available under the terms of the [GNU Affero General Public License, version 3](https://www.gnu.org/licenses/agpl-3.0.html).

## Badges

![GitHub contributors](https://img.shields.io/github/contributors/OpenLibraryProject/OpenLibrary)
![GitHub issues](https://img.shields.io/github/issues/OpenLibraryProject/OpenLibrary)
![GitHub pull requests](https://img.shields.io/github/issues-pr/OpenLibraryProject/OpenLibrary)
![GitHub forks](https://img.shields.io/github/forks/OpenLibraryProject/OpenLibrary?style=social)
![GitHub stars](https://img.shields.io/github/stars/OpenLibraryProject/OpenLibrary?style=social)
![License](https://img.shields.io/github/license/OpenLibraryProject/OpenLibrary)
