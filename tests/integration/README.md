Integration tests
=================

Browser-based integration tests via splinter

These tests are independent of the Open Library context and can be run
in any environment. They hit the actual website under test with real
requests. Some tests rely on the presence of certain data being present.

## Installation

Tested on Python 2.7.6, 2.7.12, 3.5.4

Google Chrome needs to be installed.

$ brew install chromedriver (on Mac)
$ pip install splinter
$ pip install pytest

## Running tests

Verify correct Open Library host in test files.
- Default: `http://localhost:8080`

$ cd tests/integration
$ pytest
