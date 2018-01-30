# Open Library

[![Build Status](https://travis-ci.org/internetarchive/openlibrary.svg?branch=master)](https://travis-ci.org/internetarchive/openlibrary) [![Join the chat at https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Open Library (https://openlibrary.org) is an open, editable library
catalog, building towards a web page for every book ever published.

## Table of Contents
   - [Overview](#overview)
   - [Installation](#installation)
   - [Code Organization](#code-organization)
   - [Architecture](#architecture)
     - [The Frontend](#the-frontend)
     - [The Backend](#the-backend)
     - [The Service Architecture](#the-service-architecture)
   - [Developer's Guide](#developers-guide)
   - [Running Tests](#running-tests)
   - [Contributing](#contributing)
   - [Public APIs](https://openlibrary.org/developers/api)
   - [FAQs](https://openlibrary.org/help/faq)
   - [License](#license)

## Overview

Open Library is an effort started in 2006 to create "one web page for
every book ever published". It provides access to many public domain
and out-of-print books, which can be read online.

- [Learn more about the Open Library project](https://openlibrary.org/about)
- [The Vision (Dream) of OpenLibrary](https://openlibrary.org/about/vision)
- [Visit the Blog](http://blog.openlibrary.org)

## Installation

First you need to have installed
[Virtualbox](https://www.virtualbox.org/) and
[Vagrant](https://www.vagrantup.com/).

Next, fork the [OpenLibrary repo](https://github.com/internetarchive/openlibrary) to your own [Github](https://www.github.com) account and clone your forked repo to your local machine:

        git clone git@github.com:YOURACCOUNT/openlibrary.git

Enter the project directory and provision + launch the dev virtual machine instance using vagrant:

      cd openlibrary
      vagrant up

You can now view your running instance by loading `http://localhost:8080` in a web browser.

You can turn off the virtual machine from the host machine using:

        vagrant halt
	
To administrate and ssh into the vagrant dev virtual machine, type:

        vagrant ssh

Note: Remember that, thanks to vagrant and virtual box, your local
folder `openlibrary` (where you ran `vagrant up`) contains *exactly*
the same files as `/openlibrary` in the dev virtual machine (the one
that you login to via `vagrant ssh`).

### Help!

If running in Vagrant, but services don't seem to have been properly started -- e.g. the site works but you can't login with the default credentials -- try running `vagrant up --provision`.

### Developer's Guide

For instructions on administrating your Open Library instance and
build instructions for developers, refer the Developer's
[Quickstart.md](Quickstart.md) document.

You can find more info digging into this old (and in part outdated) document here: http://code.openlibrary.org/en/latest/

## Code Organization

* openlibrary/core - core openlibrary functionality, imported and used by www
* openlibrary/plugins - other models, controllers, and view helpers
* openlibrary/views - views for rendering web pages
* openlibrary/templates - all the templates used in the website
* openlibrary/macros - macros are like templates, but can be called from wikitext

## Architecture

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

## Running tests

Open Library tests can be run using pytest (py.test).

Inside vagrant, go to the application base directory:

        cd /openlibrary
        make test

### Integration Tests

Integration tests use the Splinter webdriver with Google Chrome. For instructions on installation requirements and running integration tests, [see Integration Tests README](tests/integration/README.md)

## Contributing

[Check out our contributor's guide](CONTRIBUTING.md) to learn how you can contribute!

## License

All source code published here is available under the terms of the GNU
Affero General Public License, version 3. Please see
http://gplv3.fsf.org/ for more information.
