from infogami.utils import delegate
from openlibrary.utils.sentry import Sentry, InfogamiSentryProcessor, sentry_factory

sentry: Sentry | None = None


def setup():
    global sentry
    sentry = sentry_factory.get_instance('ol_web')

    if sentry.enabled:
        delegate.add_exception_hook(lambda: sentry.capture_exception_webpy())
        delegate.app.add_processor(InfogamiSentryProcessor(delegate.app))
