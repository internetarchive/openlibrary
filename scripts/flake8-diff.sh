#!/bin/sh

# https://flake8.readthedocs.io/en/latest/user/error-codes.html
# https://pycodestyle.readthedocs.io/en/latest/intro.html#error-codes
# https://black.readthedocs.io/en/stable/the_black_code_style.html
# E203 whitespace before ':'
# E226 missing whitespace around arithmetic operator
# F401 '._init_path' imported but unused
# W504 line break after binary operator
# W503 line break before binary operator

# FIXME: fix and update max-line-length to 88
# FIXME: F405 'translate' may be undefined, or defined from star imports: openlibrary.catalog.marc.fast_parse
# FIXME: F841 local variable assigned to but never used
# FIXME: W605 invalid escape sequence '\d'
flake8 \
  --diff \
  --filename=*.py \
  --ignore=E203,E226,F401,F405,F841,W504,W503,W605 \
  --max-line-length=1200 \
  --statistics
