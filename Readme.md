# Open Library

Open Library (https://openlibrary.org) is an open, editable library
catalog, building towards a web page for every book ever published.

[![Build Status](https://travis-ci.org/internetarchive/openlibrary.svg?branch=master)](https://travis-ci.org/internetarchive/openlibrary)

## Table of Contents
   - [Overview](#overview)
   - [Installation](#installation)
   - [Code Organization](#code-organization)
   - [Learn the Stack](#learn-the-stack)
     - [The Frontend](#the-frontend)
     - [The Backend](#the-backend)
     - [The Service Architecture](#the-service-architecture)
   - [Contributing](#contributing)
   - [Public APIs](https://openlibrary.org/developers/api)
   - [License](#license)

## Installation

See the [Quickstart.md](Quickstart.md) for instructions on setting up a developer VM.

You can find more info digging into this old (and in part outdated) document here: http://code.openlibrary.org/en/latest/

## Code Organization

* openlibrary/core - core openlibrary functionality, imported and used by www
* openlibrary/plugins - other models, controllers, and view helpers
* openlibrary/views - views for rendering web pages
* openlibrary/templates - all the templates used in the website
* openlibrary/macros - macros are like templates, but can be called from wikitext

## Learn the Stack

### The Frontend

- [Overview of Frontend Technologies](http://code.openlibrary.org/en/latest/dev/index.html)

### The Backend

OpenLibrary is developed on top of the Infogami wiki system, which is
itself built on top of the web.py Python web framework and the
Infobase database framework. 

- [Overview of Backend Web Technologies](https://openlibrary.org/about/tech)

Once you've read the overview of OpenLibrary Backend technologies,
it's highly encouraged you read the developer primer which explains
how to use Infogami (and its database, Infobase):

- [Infogami Developer Tutorial](https://openlibrary.org/dev/docs/infogami)

### The Service Architecture

- [Overview of OpenLibrary Service Architecture](https://openlibrary.org/about/architecture)

## Contributing

We'd love your help! Choose a bug from our project board:
https://github.com/internetarchive/openlibrary/projects/1

## License

All source code published here is available under the terms of the GNU
Affero General Public License, version 3. Please see
http://gplv3.fsf.org/ for more information.
