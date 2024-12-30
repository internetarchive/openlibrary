import infogami
from infogami.utils import delegate
from openlibrary.utils.sentry import InfogamiSentryProcessor, Sentry

sentry: Sentry | None = None


def setup():
    global sentry
    sentry = Sentry(getattr(infogami.config, 'sentry', {}))

    if sentry.enabled:
        sentry.init()
        delegate.add_exception_hook(lambda: sentry.capture_exception_webpy())
        delegate.app.add_processor(InfogamiSentryProcessor(delegate.app))
