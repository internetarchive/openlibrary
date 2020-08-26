import sentry_sdk

import infogami
from infogami.utils import delegate


def setup():
    if not hasattr(infogami.config, 'sentry_dns'):
        return

    sentry_sdk.init(dsn=infogami.config.get('sentry_dns'))
    delegate.add_exception_hook(lambda: sentry_sdk.capture_exception())
