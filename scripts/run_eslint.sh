#!/bin/sh
# Based on https://github.com/eslint/eslint/issues/19776 and https://github.com/pre-commit/pre-commit/issues/3321
# It seems running eslint from a bash script is the only way to have it work in pre-commit for v9.


npm i --no-audit
npx eslint --fix $1
