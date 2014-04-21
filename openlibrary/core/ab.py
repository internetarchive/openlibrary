"""A/B testing for Open Library.

Setup:

The sixpack host and alternatives for each experiment are specified in the config file.

Sample config:

sixpack_url: http://localhost:1234/
ab:
    borrow-layout:
        - one-row
        - two-rows
"""
import web
from sixpack.sixpack import Session
import logging
from infogami import config

logger = logging.getLogger("openlibrary.ab")

def get_session():
    if "sixpack_session" not in web.ctx:
        cookies = web.cookies(sixpack_id=None)
        session = Session(client_id=cookies.sixpack_id, options=_get_sixpack_options())
        if session.client_id != cookies.sixpack_id:
            web.setcookie('sixpack_id', session.client_id)
        web.ctx.sixpack_session = session
    return web.ctx.sixpack_session

def _get_sixpack_options():
    host = config.get('sixpack_url')
    return {
        'host': host
    }

def get_ab_value(testname):
    cache = web.ctx.setdefault("sixpack_cache", {})
    if testname not in cache:
        cache[testname] = participate(testname)
    return cache[testname]

def participate(testname, alternatives=None):
    if alternatives is None:
        ab_config = config.get("ab", {})
        alternatives = ab_config.get(testname)
    if alternatives:
        response = get_session().participate(testname, alternatives)
        logger.info("participate %s %s -> %s", testname, alternatives, response)
        value = response['alternative']['name']
    else:
        # default value when no alternatives are provided in config.
        value = 'control'
    return value

def convert(testname):
    logger.info("convert %s", testname)
    return get_session().convert(testname)