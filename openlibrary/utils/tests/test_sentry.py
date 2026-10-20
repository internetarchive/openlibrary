import pytest
import sentry_sdk
import web
from sentry_sdk.transport import Transport

from openlibrary.utils.sentry import InfogamiSentryProcessor, Sentry, webpy_framework_tag_processor


class RecordingTransport(Transport):
    def __init__(self):
        super().__init__()
        self.events = []

    def capture_envelope(self, envelope):
        self.events += [item.payload.json for item in envelope.items if item.type in {"event", "transaction"}]


@pytest.fixture
def sentry_events():
    transport = RecordingTransport()
    global_scope = sentry_sdk.get_global_scope()
    previous_client = global_scope.client
    with sentry_sdk.isolation_scope() as scope, sentry_sdk.new_scope():
        sentry_sdk.init(dsn="http://test@localhost/1", transport=transport, traces_sample_rate=1.0, default_integrations=False)
        scope.set_client(global_scope.client)
        try:
            yield transport.events
        finally:
            global_scope.client.close()
            global_scope.set_client(previous_client)


def test_webpy_events_are_tagged(sentry_events, monkeypatch):
    sentry = Sentry({})

    class Page:
        def GET(self):
            return "ok"

    def outer_processor(handler):
        # Like layout_processor, which runs outside InfogamiSentryProcessor.
        if web.ctx.path == "/error":
            raise ValueError("processor error")
        return handler()

    app = web.application(("/", "Page", "/error", "Page"), {"Page": Page})
    _internalerror = app.internalerror

    def internalerror():
        sentry.capture_exception_webpy()
        return _internalerror()

    app.internalerror = internalerror
    app.add_processor(webpy_framework_tag_processor)
    app.add_processor(outer_processor)
    app.add_processor(InfogamiSentryProcessor(app))
    monkeypatch.setattr(InfogamiSentryProcessor, "find_route_name", lambda self: "/")

    app.request("/")
    app.request("/error")
    sentry_sdk.capture_message("outside a request")

    *request_events, outside_event = sentry_events
    assert sorted(event.get("type", "event") for event in request_events) == ["event", "transaction"]
    assert all(event["tags"]["framework"] == "webpy" for event in request_events)
    assert "framework" not in outside_event.get("tags", {})
