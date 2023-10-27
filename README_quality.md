Quality code
============

Be confident in changing files you can check the quality (linter) with [pre-commit](https://pre-commit.com/index.html)
Pre-commit is used to inspect the snapshot that is about to be committed, to see if you missed anything, or to review what you need to inspect in the code. You can see the actions descriptions in the **pre-commit-config.yml** file.

The pre-commit is launched for PR validations, it is important to install the pre-commit locally to avoid unverified code being pushed.

## Installation

````
pip install pre-commit
 or
$ brew install pre-commit (Homebrew)

$ pre-commit install
````

After executing the last command, when you normally run ``git commit``, pre-commit will also perform its checks.

## Running (manually)

To run the pre-commit

````
$ pre-commit run --files pre-commit-config.yml
````