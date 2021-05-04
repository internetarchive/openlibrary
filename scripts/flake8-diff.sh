#!/bin/sh

# https://flake8.readthedocs.io/en/latest/user/error-codes.html
# https://pycodestyle.readthedocs.io/en/latest/intro.html#error-codes
# https://black.readthedocs.io/en/stable/the_black_code_style.html
# E203 whitespace before ':'
# E226 missing whitespace around arithmetic operator
# F401 '._init_path' imported but unused
# W504 line break after binary operator
# W503 line break before binary operator
flake8 \
  --diff \
  --filename=*.py \
  --ignore=E203,E226,F401,W504,W503 \
  --max-line-length=88 \
  --statistics
