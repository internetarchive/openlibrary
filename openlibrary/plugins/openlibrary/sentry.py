from typing import Optional

import infogami
from infogami.utils import delegate
from openlibrary.utils.sentry import Sentry, SentryProcessor

sentry: Optional[Sentry] = None


def setup():
    global sentry
    sentry = Sentry(getattr(infogami.config, 'sentry', {}))

    if sentry.enabled:
        sentry.init()
        delegate.add_exception_hook(lambda: sentry.capture_exception_webpy())
        delegate.app.add_processor(SentryProcessor())
