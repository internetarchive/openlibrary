"""Interface to access the database of openlibrary.
"""
import web

@web.memoize
def get_db():
    """Returns an instance of webpy database object.

    The database object is cached so that one object is used everywhere.
    """
    return web.database(**web.config.db_parameters)
