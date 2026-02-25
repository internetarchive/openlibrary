import infogami
from infogami.utils import delegate
from openlibrary.utils.sentry import InfogamiSentryProcessor, Sentry, init_sentry

sentry: Sentry | None = None


def setup():
    global sentry
    if sentry is not None:
        # Avoid attaching exception hooks multiple times
        return

    sentry = init_sentry(getattr(infogami.config, 'sentry', {}))

    if sentry.enabled:
        delegate.add_exception_hook(sentry.capture_exception_webpy)
        delegate.app.add_processor(InfogamiSentryProcessor(delegate.app))
