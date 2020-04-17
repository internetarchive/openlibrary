#!/bin/sh

# https://flake8.readthedocs.io/en/latest/user/error-codes.html
# https://pycodestyle.readthedocs.io/en/latest/intro.html#error-codes
# E226 missing whitespace around arithmetic operator
# F401 '._init_path' imported but unused
# W504 line break after binary operator
flake8 --diff --ignore=E226,F401,W504 --max-line-length=88 --statistics
