#!/bin/sh

# https://flake8.readthedocs.io/en/latest/user/error-codes.html
# https://pycodestyle.readthedocs.io/en/latest/intro.html#error-codes
# E226 missing whitespace around arithmetic operator
# F401 '._init_path' imported but unused
# W504 line break after binary operator
# flake8 --diff --filename=*.py --ignore=E203,E226,F401,W503 --max-line-length=88 --statistics
flake8 --diff --filename=*.py --select=E9,F63,F7,F82  --max-line-length=256 --statistics
