Integration tests
=================

Browser-based integration tests via splinter

These tests are independent of the Open Library context and can be run
in any environment. They hit the actual website under test with real
requests. Some tests rely on the presence of certain data being present.

## Installation

Tested on Python 2.7.6, 2.7.18, 3.8.5

Google Chrome needs to be installed.

````
$ port install chromedriver (MacPorts)
 or
$ brew install chromedriver (Homebrew)

$ python3 -m venv .venv
$ source .venv/bin/activate
$ python3 -m pip install --upgrade pip
$ python3 -m pip install pytest pyyaml splinter
Install Chrome and Chromedriver (see .travis.yml) for FireFox and Gekodriver
* More info at https://chromedriver.chromium.org/
````

## Running tests

Run Open Library in Docker as discussed at:
https://github.com/internetarchive/openlibrary/tree/master/docker

Verify correct Open Library host in test files.
- Default: `http://localhost:8080`

For now, need to manually add an Edition to a new List just once.

````
$ pytest tests/integration
````
