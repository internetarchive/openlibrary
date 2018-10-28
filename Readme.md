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

### Vagrant (Legacy & Windows)

First you need to have installed [Virtualbox](https://www.virtualbox.org/) and [Vagrant](https://www.vagrantup.com/).

Next, fork the [OpenLibrary repo](https://github.com/internetarchive/openlibrary) to your own [Github](https://www.github.com) account and clone your forked repo to your local machine:

```
git clone git@github.com:YOURACCOUNT/openlibrary.git
```

##### For Windows Users Only

1. Before proceeding further, kindly make sure to set the line endings to type `input` by executing the below command:

```bash
# Configure Git on Windows to properly handle line endings so Git will convert CRLF to LF on commit
git config --global core.autocrlf input
```

Enter the project directory and provision + launch the dev virtual machine instance using vagrant:

```bash
cd openlibrary
vagrant up
```

##### For Windows Users Only

1. If dev virtual machine instance doesn't start by any chance and throws an error `No module found` then you need to check whether `symlinks` are enabled or not. The `openlibrary` makes use of symlinks, which by default git on windows checks out as plain text files. You can check that by executing below command:

```bash
git config core.symlinks
```

2. If `symlinks` are enabled then go to the next step. If `symlinks` are not enabled then enable it by executing below command:

```bash
git config core.symlinks true
```

3. Then hard reset the repo so git will create proper symlinks by executing below command:

```bash
git reset --hard HEAD
```

**Note:** <br>
If you get permission issue while executing any above commands then kindly run the git bash shell as an Administrator.

You can now view your running instance by loading `http://localhost:8080` in a web browser.

You can turn off the virtual machine from the host machine using:
```
vagrant halt
```	

To administrate and ssh into the vagrant dev virtual machine, type:

```
vagrant ssh
```

**Note:** <br>
Remember that, thanks to vagrant and virtual box, your local folder `openlibrary` (where you ran `vagrant up`) contains *exactly* the same files as `/openlibrary` in the dev virtual machine (the one that you login to via `vagrant ssh`).

### Reload vagrant services:

- From within vagrant restart the Open Library service via:
``` sudo systemctl restart ol-web. ``` <br>
- If you are not in the vagrant dev virtual machine you can simply run ``` vagrant reload ``` for the same.

### Help!

If running in Vagrant, but services don't seem to have been properly started -- e.g. the site works but you can't login with the default credentials -- try running `vagrant up --provision`.

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

Inside vagrant, go to the application base directory:

```
cd /openlibrary
make test
```

### Integration Tests

Integration tests use the Splinter webdriver with Google Chrome. For instructions on installation requirements and running integration tests, [see Integration Tests README](tests/integration/README.md)
