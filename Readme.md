# Open Library

[![Build Status](https://travis-ci.org/internetarchive/openlibrary.svg?branch=master)](https://travis-ci.org/internetarchive/openlibrary) [![Join the chat at https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

[Open Library](https://openlibrary.org) is an open, editable library catalog, building towards a web page for every book ever published.

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
   - [Contributing](CONTRIBUTING.md)
   - [Public APIs](https://openlibrary.org/developers/api)
   - [FAQs](https://openlibrary.org/help/faq)
   - [License](LICENSE)

## Overview

Open Library is an effort started in 2006 to create "one web page for every book ever published". It provides access to many public domain and out-of-print books, which can be read online.

- [Learn more about the Open Library project](https://openlibrary.org/about)
- [The Vision (Dream) of OpenLibrary](https://openlibrary.org/about/vision)
- [Visit the Blog](http://blog.openlibrary.org)

## Installation

### Docker
**We're supporting Docker, moving forward**. If you are a new contributor, especially on linux, please consider setting up using the [Docker Instructions](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md).

[![Open Library Docker Tutorial](https://user-images.githubusercontent.com/978325/47388313-ada5e800-d6c6-11e8-9501-fc04e3152f20.png)](https://archive.org/embed/openlibrary-developer-docs/zoom_0.mp4?autoplay=1&start=2)

Our `Docker` environment is in active development. Want to contribute? Here's our top-level [`Docker` todo-list](https://github.com/internetarchive/openlibrary/issues/1067) and a [list of open `Docker` issues](https://github.com/internetarchive/openlibrary/issues?utf8=%E2%9C%93&q=is%3Aissue+is%3Aopen+label%3Adocker).

### Developer's Guide

For instructions on administrating your Open Library instance and build instructions for developers, refer the Developer's [Quickstart](https://github.com/internetarchive/openlibrary/wiki/Getting-Started) Guide.

You can also find more information regarding Developer Documentation for Open Library in the Open Library [Wiki](https://github.com/internetarchive/openlibrary/wiki/)

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

Once you've read the overview of OpenLibrary Backend technologies, it's highly encouraged you read the developer primer which explains how to use Infogami (and its database, Infobase):

- [Infogami Developer Tutorial](https://openlibrary.org/dev/docs/infogami)

## Running tests

Open Library tests can be run using pytest. Kindly look up on our [Testing Document](https://github.com/internetarchive/openlibrary/wiki/Testing) for more details

Run tests while the docker container is running

```
cd docker/
docker-compose exec web make test
```

### Integration Tests

Integration tests use the Splinter webdriver with Google Chrome. For instructions on installation requirements and running integration tests, [see Integration Tests README](tests/integration/README.md)
