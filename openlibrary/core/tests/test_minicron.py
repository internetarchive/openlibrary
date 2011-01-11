"""
Tests to test the minicron implementation.

A simple cron substitute for the dev instance.
"""

import os
import time
import datetime

import pytest

from openlibrary.core import minicron

def test_nonexistentinputfile(dummy_crontabfile):
    "Create a cron parser with an non existent input file"
    cron = minicron.Minicron("/non/existent/file.tests", None, 0.01)
    pytest.raises(IOError, cron.run)

def test_malformed_cron_line(dummy_crontabfile):
    cron = minicron.Minicron(dummy_crontabfile, 1)
    d = datetime.datetime.now()
    pytest.raises(minicron.BadCronLine, cron._matches_cron_expression, d, "* * 5 * * do_something")

def test_ticker(dummy_crontabfile, monkeypatch, counter):
    "Checks that the ticker executes once a minute"
    cron = minicron.Minicron(dummy_crontabfile, None, 0.1) # Make the clock tick once in 0.1 seconds (so that the test finishes quickly)
    monkeypatch.setattr(cron, '_tick', counter(cron._tick))
    cron.run(3) 
    assert cron._tick.invocations == 3, "Ticker ran %d times (should be 3)"%cron._tick.invocations

def test_cronline_parser_everyminute(dummy_crontabfile):
    "Checks the cronline parser for executing every minute/hour"
    cron = minicron.Minicron(dummy_crontabfile, 1)
    d = datetime.datetime.now()
    assert cron._matches_cron_expression(d, "* * * * * do_something"), "* * * * * should be executed every minute/hour but isn't"

def test_cronline_parser_fifthminuteofeveryhour(dummy_crontabfile):
    "Checks the cronline parser for executing at the fifth minute of every hour"
    cron = minicron.Minicron(dummy_crontabfile, 1)
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, "5 * * * * do_something") == False, "5 * * * * should be executed only at the fifth minute but is executed at the first"
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 5, second = 0)
    assert cron._matches_cron_expression(d, "5 * * * * do_something"), "5 * * * * should be executed at the fifth minute but is not"

def test_cronline_parser_everyfifthminute(dummy_crontabfile):
    "Checks the cronline parser for executing at every fifth minute"
    cron = minicron.Minicron(dummy_crontabfile, 1)
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 2, second = 0)
    assert cron._matches_cron_expression(d, "*/5 * * * * do_something") == False, "*/5 * * * * should be executed only at every fifth minute but is executed at the second"
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 5, second = 0)
    assert cron._matches_cron_expression(d, "*/5 * * * * do_something"), "*/5 * * * * should be executed at the fifth minute but is not"

def test_cronline_parser_thirdhourofeveryday(dummy_crontabfile):
    "Checks the cronline parser for executing at the third hour of every day"
    cron = minicron.Minicron(dummy_crontabfile, 1)
    expression = "* 3 * * * do_something"
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, expression) == False, " %s should be executed only at the third hour but is executed at the first"%expression
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 3, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, expression), "%s should be executed at the third hour but is not"%expression
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 6, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, expression) == False, "%s should not be executed in the 6th hour but it is"%expression

def test_cronline_parser_everythirdhour(dummy_crontabfile):
    "Checks the cronline parser for executing every third hour"
    cron = minicron.Minicron(dummy_crontabfile, 1)
    expression = "* */3 * * * do_something"
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 1, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, expression) == False, " %s should be executed only every third hour but is executed at the first"%expression
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 3, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, expression), "%s should be executed at the third hour but is not"%expression
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 6, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, expression), "%s should be executed at the sixth hour but is not"%expression
    d = datetime.datetime(year = 2010, month = 8, day = 10, hour = 5, minute = 1, second = 0)
    assert cron._matches_cron_expression(d, expression) == False, "%s should not be executed at the fifth hour but it is"%expression

def test_cronline_running(crontabfile):
    "Checks if the cron actually executes commands"
    assert not os.path.exists("/tmp/crontest") # Make sure that out test file doesn't exist
    cron = minicron.Minicron(crontabfile, None, 0.1)
    cron.run(1)
    assert os.path.exists("/tmp/crontest"), "/tmp/crontest should have been created by the cron but its not"
    os.unlink("/tmp/crontest")

def test_proper_run(monkeypatch, counter):
    "Tries a cron run with a non-trivial time pattern"
    cronfile = os.tmpnam()
    f = open(cronfile,"w")
    f.write("*/2 0 * * * touch /tmp/foo\n") # Every alternate minute in the first hour only
    f.close()
    cron = minicron.Minicron(cronfile, datetime.datetime(hour =0, minute = 0, second = 0, year = 2011, month = 1, day =1), 0.01)
    monkeypatch.setattr(cron, '_run_command', counter(cron._run_command))
    cron.run(120) # Run for 2 hours
    assert cron._run_command.invocations == 29, "The function should have run every alternate minute in the first hour (29 times) but ran %s times"%cron._run_command.invocations 

    f = open(cronfile,"w")
    f.write("*/2 0 * * * touch /tmp/foo\n") # Every alternate minute in the first hour only
    f.write("* 1 * * * touch /tmp/foo\n") # Every minute in the second hour
    f.close()
    cron = minicron.Minicron(cronfile, datetime.datetime(hour =0, minute = 0, second = 0, year = 2011, month = 1, day =1), 0.01)
    monkeypatch.setattr(cron, '_run_command', counter(cron._run_command))
    cron.run(180) # Run for 3 hours
    assert cron._run_command.invocations == 89, "The function should have run every alternate minute in the first hour (29 times) and every minute in the second (60 times) i.e. totally 89 times but ran %s times"%cron._run_command.invocations

    f = open(cronfile,"w")
    f.write("1 1 * * * touch /tmp/foo\n") # Every alternate minute in the first hour only
    f.close()
    cron = minicron.Minicron(cronfile, datetime.datetime(hour =0, minute = 0, second = 0, year = 2011, month = 1, day =1), 0.01)
    monkeypatch.setattr(cron, '_run_command', counter(cron._run_command))
    cron.run(180) # Run for 3 hours
    assert cron._run_command.invocations == 1, "The function should have run just once in the second minute of the second hour but ran %s times"%cron._run_command.invocations

    
