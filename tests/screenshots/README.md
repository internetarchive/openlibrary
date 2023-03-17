Screenshot tests
================

Be confident in changing styles by seeing what effect it has across pages.

## Installation

````
$ port install node (MacPorts)
 or
$ brew install node (Homebrew)

$ npm install --no-audit
````

## Running tests

First check out the `master` branch and run:

````
$ npm run generate-expected
````

This saves the screenshots in the `expected` directory.

Then make your changes, and run:

````
$ npm run generate-actual
````

This saves the screenshots in the `actual` directory.

Then generate a report:

````
$ npm run generate-report
````

Now open `report.html` and make sure all your changes are indeed intended.

## Future

Ideally these steps would be run in Travis CI, with the final report being posted
to the Pull Request, e.g. using https://github.com/reg-viz/reg-suit. This is mostly
blocked on Docker, since when we have Docker we can start a server in Travis CI.
