"""
Tests to test the minicron implementation.

A simple cron substitute for the dev instance.
"""


def test_sanity(crontabfile):
    "Create a simple cron parser with an input file"
    from openlibrary.core import minicron
    cron = minicron.Minicron(crontabfile)
    
    
