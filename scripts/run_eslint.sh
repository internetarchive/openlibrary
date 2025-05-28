#!/bin/sh
# Based on https://github.com/eslint/eslint/issues/19776 and https://github.com/pre-commit/pre-commit/issues/3321
# It seems running eslint from a bash script is the only way to have it work in pre-commit for v9.


# npm i eslint@9.27.0 eslint-plugin-no-jquery@3.1.1 eslint-plugin-vue@10.1.0 @babel/eslint-parser@7.27.1 @babel/plugin-syntax-dynamic-import@7.8.3 @babel/preset-env@7.24.7
npx eslint --fix $1
