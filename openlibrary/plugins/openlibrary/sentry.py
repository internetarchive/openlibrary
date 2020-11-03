import logging
from subprocess import PIPE, Popen, STDOUT

import sentry_sdk

import infogami
from infogami.utils import delegate

logger = logging.getLogger("openlibrary.sentry")


def is_enabled():
    return hasattr(infogami.config, 'sentry') and infogami.config.sentry.enabled


def get_software_version():  # -> str:
    cmd = "git rev-parse --short HEAD --".split()
    return str(Popen(cmd, stdout=PIPE, stderr=STDOUT).stdout.read().decode().strip())


def setup():
    logger.info("Setting up sentry (enabled={})".format(is_enabled()))

    if not is_enabled():
        return

    sentry_sdk.init(dsn=infogami.config.sentry.dsn,
                    environment=infogami.config.sentry.environment,
                    release=get_software_version())
    delegate.add_exception_hook(lambda: sentry_sdk.capture_exception())
