Integration tests and quality
============================

Browser-based integration tests via splinter

These tests are independent of the Open Library context and can be run
in any environment. They hit the actual website under test with real
requests. Some tests rely on the presence of certain data being present.

## Installation

Tested on Python 2.7.6, 2.7.12, 3.5.4

Google Chrome needs to be installed.

````
$ port install chromedriver (MacPorts)
 or
$ brew install chromedriver (Homebrew)

$ source activate openlibrary
$ pip install splinter
$ pip install pytest
$ pip install pyyaml
````

## Running tests

Verify correct Open Library host in test files.
- Default: `http://localhost:8080`

For now, need to manually add an Edition to a new List just once.

````
$ cd tests/integration
$ pytest
````

## Check your quality (with pre-commit)

Pre-commit is used to inspect the snapshot that is about to be committed, to see if you missed anything, or to review what you need to inspect in the code. You can see the actions descriptions in the **pre-commit-config.yml** file.

Install the [pre-commit](https://pre-commit.com/index.html)

````
$ pip install pre-commit
 or
$ brew install pre-commit (Homebrew)

$ pre-commit install
````

To run the pre-commit

````
$ pre-commit run --files pre-commit-config.yml
````