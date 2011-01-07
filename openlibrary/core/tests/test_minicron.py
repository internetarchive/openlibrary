"""
Tests to test the minicron implementation.

A simple cron substitute for the dev instance.
"""

import datetime

import pytest

from openlibrary.core import minicron

def test_sanity(crontabfile):
    "Create a simple cron parser with an input file"
    cron = minicron.Minicron(crontabfile)
    # pytest.raises(IOError, minicron.Minicron, "/non/existent/file.tests")

def test_ticker(crontabfile, monkeypatch, counter):
    "Checks that the ticker executes once a minute"
    cron = minicron.Minicron(crontabfile, 1) # Make the clock tick once a second (so that the test finishes quickly)
                                             # A minute is scaled down a second now
    monkeypatch.setattr(cron, '_tick', counter(cron._tick))
    cron.run(5) 
    assert cron._tick.invocations == 5, "Ticker ran %d times (should be 5)"%cron._tick.invocations


def test_cronline_parser_everyminute(crontabfile):
    "Checks the cronline parser for executing every minute"
    cron = minicron.Minicron(crontabfile, 1)
    d = datetime.datetime.now()
    assert cron._matches_cron_expression(d, "* * * * * do_something"), "* * * * * should be executed every minute"

def test_cronline_parser_fifthminuteofeveryhour(crontabfile):
    "Checks the cronline parser for executing at the fifth minute of every hour"
    cron = minicron.Minicron(crontabfile, 1)
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, "5 * * * * do_something") == False, "5 * * * * should be executed only at the fifth minute but is executed at the first"
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 5, second = 0)
    assert cron._matches_cron_expression(d, "5 * * * * do_something"), "5 * * * * should be executed at the fifth minute but is not"

def test_cronline_parser_everyfifthminute(crontabfile):
    "Checks the cronline parser for executing at every fifth minute"
    cron = minicron.Minicron(crontabfile, 1)
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 2, second = 0)
    assert cron._matches_cron_expression(d, "*/5 * * * * do_something") == False, "*/5 * * * * should be executed only at every fifth minute but is executed at the second"
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 5, second = 0)
    assert cron._matches_cron_expression(d, "*/5 * * * * do_something"), "*/5 * * * * should be executed at the fifth minute but is not"


    
    
    

# def test_runner_everyminute(tmpdir, monkeypatch, counter):
#     "Checks that execution happens every minute for a * * * * * cron line"
#     p = tmpdir.mkdir("crontab").join("every-minute")
#     p.write("* * * * * echo 'hello'")
#     cron = minicron.Minicron(p, 1)
#     monkeypatch.setattr(cron, '_tick', counter(cron._tick))
#     monkeypatch.setattr(cron, '_execute', counter(cron._execute))
#     cron.run(5)
#     assert cron._execute_command.invocations == 5, "Command was executed %d times (should be 5)"%cron._execute.invocations
#     assert cron._execute_command.invocations == 5, "Command was executed %d times (should be 5)"%cron._execute.invocations
    
