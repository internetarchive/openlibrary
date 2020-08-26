import sentry_sdk

import infogami
from infogami.utils import delegate


def setup():
    if infogami.config.sentry.enabled != 'true':
        return

    sentry_sdk.init(dsn=infogami.config.sentry.dsn,
                    environment=infogami.config.sentry.environment)
    delegate.add_exception_hook(lambda: sentry_sdk.capture_exception())
