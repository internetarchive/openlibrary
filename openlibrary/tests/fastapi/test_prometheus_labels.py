from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from openlibrary.utils import prometheus
from openlibrary.utils.request_context import Visitor, visitor


def test_metrics_are_labelled_fastapi(monkeypatch):
    # Its own registry: other apps' tests (e.g. coverstore's) register the same metrics in the default one
    registry = CollectorRegistry()
    request_metrics = prometheus.request_metrics
    monkeypatch.setattr(prometheus, "request_metrics", lambda server: request_metrics(server, registry=registry))
    monkeypatch.setattr("openlibrary.asgi_app.set_context_from_fastapi", lambda request: None)
    from openlibrary.asgi_app import create_app  # noqa: PLC0415

    with TestClient(create_app()) as client:
        client.get("/no-such-route")

    labels = {"handler": "none", "method": "GET", "server": "fastapi", "status": "404", "visitor": "anonymous", "response_type": "json"}
    assert registry.get_sample_value("http_requests_total", labels) == 1


def test_fastapi_counts_a_librarian_marked_by_the_route(monkeypatch):
    registry = CollectorRegistry()
    request_metrics = prometheus.request_metrics
    monkeypatch.setattr(prometheus, "request_metrics", lambda server: request_metrics(server, registry=registry))
    monkeypatch.setattr("openlibrary.asgi_app.set_context_from_fastapi", lambda request: visitor.set(Visitor(user_key="/people/alice")))
    from openlibrary.asgi_app import create_app  # noqa: PLC0415

    app = create_app()

    # A sync route runs in a worker thread, like most is_librarian_or_higher() calls; the metric must still see the mark
    @app.get("/librarian-page")
    def librarian_page():
        visitor.get().is_librarian = True
        return {}

    with TestClient(app) as client:
        client.get("/librarian-page")

    labels = {"handler": "/librarian-page", "method": "GET", "server": "fastapi", "visitor": "librarian", "response_type": "json"}
    assert registry.get_sample_value("http_request_duration_seconds_count", labels) == 1
    assert registry.get_sample_value("http_requests_total", labels | {"status": "200"}) == 1
