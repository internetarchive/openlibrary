import logging

import sentry_sdk

import infogami
from infogami.utils import delegate

from openlibrary.plugins.openlibrary.status import get_software_version

logger = logging.getLogger("openlibrary.sentry")


def is_enabled():
    return hasattr(infogami.config, 'sentry') and infogami.config.sentry.enabled


def setup():
    logger.info("Setting up sentry (enabled={})".format(is_enabled()))

    if not is_enabled():
        return

    sentry_sdk.init(dsn=infogami.config.sentry.dsn,
                    environment=infogami.config.sentry.environment,
                    release=get_software_version())
    delegate.add_exception_hook(lambda: sentry_sdk.capture_exception())
