# Open Library

![Python Build](https://github.com/internetarchive/openlibrary/actions/workflows/javascript_tests.yml/badge.svg)
![JS Build](https://github.com/internetarchive/openlibrary/actions/workflows/python_tests.yml/badge.svg)
[![Join the chat at https://gitter.im/theopenlibrary/Lobby](https://badges.gitter.im/theopenlibrary/Lobby.svg)](https://gitter.im/theopenlibrary/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)

[Open Library](https://openlibrary.org) is an open, editable library catalog, building towards a web page for every book ever published.

Are you looking to get started? [This is the guide](https://github.com/internetarchive/openlibrary/blob/master/CONTRIBUTING.md) you are looking for. You may wish to learn more about [Google Summer of Code (GSoC)?](https://github.com/internetarchive/openlibrary/wiki/Google-Summer-of-Code) or [Hacktoberfest](https://github.com/internetarchive/openlibrary/wiki/Hacktoberfest).

# Table of Contents
   - [Overview](#overview)
   - [Installation](#installation)
   - [Developer's Guide](#developers-guide)
   - [Code Organization](#code-organization)
   - [Architecture](#architecture)
     - [The Frontend](#the-frontend)
     - [The Backend](#the-backend)
     - [The Service Architecture](#the-service-architecture)
   - [Running Tests](#running-tests)
     - [Integration Tests](#integration-tests)
   - [Contributing](CONTRIBUTING.md)
   - [Public APIs](https://openlibrary.org/developers/api)
   - [FAQs](https://openlibrary.org/help/faq)
   - [License](#license)

## Overview

Open Library is an effort started in 2006 to create "one web page for every book ever published". It provides access to many public domain and out-of-print books, which can be read online.

Here's a quick public tour of Open Library to get your familiar with the service and its offerings (10min)

[![archive org_embed_openlibrary-tour-2020 (1)](https://user-images.githubusercontent.com/978325/91348906-55940d00-e799-11ea-83b9-17cd4d99642b.png)](https://archive.org/embed/openlibrary-tour-2020/openlibrary.ogv)

- [Learn more about the Open Library project](https://openlibrary.org/about)
- [The Vision (Dream) of OpenLibrary](https://openlibrary.org/about/vision)
- [Visit the Blog](https://blog.openlibrary.org)

## Installation

The development environment can be set up using the [Docker Instructions](https://github.com/internetarchive/openlibrary/blob/master/docker/README.md). You can also watch the [video tutorial](https://archive.org/embed/openlibrary-developer-docs/openlibrary-docker-set-up.mp4) for a more detailed explanation.

### Step-1

#### For Windows Users

**Note:** If you get permission issues while executing these commands please run git bash shell as an Administrator.

***Run the following code***
```bash
# Configure Git to convert CRLF to LF line endings on commit
git config --global core.autocrlf input

# Enable Symlinks
git config core.symlinks true

# Reset the repo (removes any changes you've made to files!)
git reset --hard HEAD
```

#### For M1 Chip (Apple Silicon) Mac Users

You will likely need to install Rosetta 2 in order to run Docker on your machine. This can be manually installed by running the following in your command line:
***Run the following code***
```
softwareupdate --install-rosetta
```
***Alternatively***, if you do not want to set up Open Library on your local computer, try Gitpod!
 This lets you work on Open Library entirely in your browser without having to install anything on your personal computer.
 Warning: This integration is still experimental.
 [![Open In Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/internetarchive/openlibrary/)
 If you setup using Gitpod, no need to follow any steps below.
 
### Step-2

#### Install Docker Desktop on Windows
Download Link : https://docs.docker.com/docker-for-windows/install/

#### Install Docker Desktop on M1 Chip (Apple Silicon) Mac
Download Link : https://docs.docker.com/docker-for-mac/apple-silicon/

#### Install Docker Desktop on Intel Chip Mac
Download Link : https://docs.docker.com/docker-for-mac/install/

### Step-3

#### Clone the OpenLibrary Project inside your local machine.
 [Here is a handy cheat sheet](https://github.com/internetarchive/openlibrary/wiki/Git-Cheat-Sheet) if you are new to using Git.

### Step-4

#### Install Docker Images

Inside your Windows/Mac terminal, run the following command under the openlibrary project directory.
```
docker-compose up
```
It may take around 10-15 minutes to install all the required openlibrary docker images and dependencies on your machine.
After successful installation, DONOT close the terminal.

### Step-5
Now open a new terminal tab/window (without closing previous terminal) and be sure to be in the openlibrary project directory, if not, then change the directory to your openlibrary project directory.

To see whether you have successfully setup the environment-
Open up your browser and enter-
```
https://localhost:8080
```
If you get directed to openlibrary home page, you have successfully set up the environment for OpenLibrary on your machine!!
Now you can start contributing. We recommend you to start by first contributing to some good-first-issues.
Here are some good-first-issues we picked up for you [click here](https://github.com/internetarchive/openlibrary/contribute)

***Note***
If you want to close the running terminal, press `Ctrl C`.

## Developer's Guide

For instructions on administrating your Open Library instance, refer to the Developer's [Quickstart](https://github.com/internetarchive/openlibrary/wiki/Getting-Started) Guide. 

You can also find more information regarding Developer Documentation for Open Library in the Open Library [Wiki](https://github.com/internetarchive/openlibrary/wiki/)

## Code Organization

* openlibrary/core - core openlibrary functionality, imported and used by www
* openlibrary/plugins - other models, controllers, and view helpers
* openlibrary/views - views for rendering web pages
* openlibrary/templates - all the templates used in the website
* openlibrary/macros - macros are like templates, but can be called from wikitext

## Architecture

### The Frontend

Click [here](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide) for a detailed Frontend guide.

### The Backend

OpenLibrary is developed on top of the Infogami wiki system, which is itself built on top of the web.py Python web framework and the Infobase database framework. 

- [Overview of Backend Web Technologies](https://openlibrary.org/about/tech)

Once you've read the overview of OpenLibrary Backend technologies, it's highly encouraged you read the developer primer which explains how to use Infogami (and its database, Infobase)

- [Infogami Developer Tutorial](https://openlibrary.org/dev/docs/infogami)

If you want to dive into the source code for Infogami, see the [Infogami repo](https://github.com/internetarchive/infogami).

### The service architecture

Click [here](https://github.com/internetarchive/openlibrary/wiki/Production-Service-Architecture) for a detailed documentation on Production Service Architecture.

## Running tests

Open Library tests can be run using pytest. Kindly look up on our [Testing Document](https://github.com/internetarchive/openlibrary/wiki/Testing) for more details

Run tests while the docker container is running

```
cd docker/
docker-compose exec web make test
```

### Integration Tests

Integration tests use the Splinter webdriver with Google Chrome. For instructions on installation requirements and running integration tests, [see Integration Tests README](tests/integration/README.md)

## License

All source code published here is available under the terms of the [GNU Affero General Public License, version 3](https://www.gnu.org/licenses/agpl-3.0.html).


