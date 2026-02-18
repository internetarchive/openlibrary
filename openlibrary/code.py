"""Main entry point for openlibrary app.

Loaded from Infogami plugin mechanism.
"""

import logging
import logging.config
import os
import sys

import infogami
from infogami.utils.app import pages
from openlibrary.plugins.admin.code import setup as admin_setup
from openlibrary.plugins.books.code import setup as books_setup
from openlibrary.plugins.importapi.code import setup as importapi_setup
from openlibrary.plugins.inside.code import setup as inside_setup
from openlibrary.plugins.openlibrary import deprecated_handler
from openlibrary.plugins.openlibrary.code import setup as openlibrary_setup
from openlibrary.plugins.upstream.code import setup as upstream_setup
from openlibrary.plugins.worksearch.code import setup as worksearch_setup


def setup():
    setup_logging()

    logger = logging.getLogger("openlibrary")
    logger.info("Application init")

    # Calling the setup function itself may not be strictly needed in all cases.
    # However, by importing the functions, we ensure the side effects are executed.
    openlibrary_setup()
    worksearch_setup()
    inside_setup()
    books_setup()
    admin_setup()
    upstream_setup()
    importapi_setup()

    # Register deprecated endpoint handlers AFTER all plugins have loaded
    # This must be done here, after all plugins are imported, to ensure our handlers
    # override the deprecated ones
    # This is only temporary while we move to fastapi

    for path in deprecated_handler.DEPRECATED_PATHS:
        if path not in pages:
            pages[path] = {}
        old_handler = pages[path].get('json')
        print(
            f"DEBUG [openlibrary/code.py]: Registering deprecated handler for {path}, old handler was: {old_handler}",
            file=sys.stderr,
        )
        pages[path]['json'] = deprecated_handler.DeprecatedEndpointHandler

    load_views()

    # load actions
    from . import actions  # noqa: F401 side effects may be needed

    logger.info("loading complete.")


def setup_logging():
    """Reads the logging configuration from config file and configures logger."""
    try:
        logconfig = infogami.config.get("logging_config_file")
        if logconfig and os.path.exists(logconfig):
            logging.config.fileConfig(logconfig, disable_existing_loggers=False)
    except Exception as e:
        print("Unable to set logging configuration:", str(e), file=sys.stderr)
        raise


def load_views():
    """Registers all views by loading all view modules."""
    from .views import showmarc  # noqa: F401 side effects may be needed


setup()
