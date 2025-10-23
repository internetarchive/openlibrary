"""Main entry point for openlibrary app.

Loaded from Infogami plugin mechanism.
"""

import logging
import logging.config
import os
import sys

import infogami
from infogami.utils import delegate, i18n, macro, template

old_plugins = [
    "openlibrary",
    "worksearch",
    "inside",
    "books",
    "admin",
    "upstream",
    "importapi",
    "recaptcha",
]


def setup():
    setup_logging()

    logger = logging.getLogger("openlibrary")
    logger.info("Application init")

    for p in old_plugins:
        logger.info("loading plugin %s", p)
        modname = f"openlibrary.plugins.{p}.code"
        path = "openlibrary/plugins/" + p
        template.load_templates(path, lazy=True)
        macro.load_macros(path, lazy=True)
        i18n.load_strings(path)
        __import__(modname, globals(), locals(), ['plugins'])

    delegate.plugins += [
        delegate._make_plugin_module('openlibrary.plugins.' + name)
        for name in old_plugins
    ]

    load_views()

    # load actions
    from . import actions  # noqa: F401, PLC0415  side effects may be needed

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
    from .views import showmarc  # noqa: F401, PLC0415  side effects may be needed


setup()
