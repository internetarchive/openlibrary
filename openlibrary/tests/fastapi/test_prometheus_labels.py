import pytest
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

    labels = {"handler": "none", "method": "GET", "server": "fastapi", "status": "404", "visitor": "anonymous"}
    assert registry.get_sample_value("http_requests_total", labels) == 1


@pytest.mark.parametrize(
    ("user_key", "path", "label"),
    [(None, "/librarian-page", "anonymous"), ("/people/alice", "/no-such-route", "user"), ("/people/alice", "/librarian-page", "librarian")],
)
def test_fastapi_records_the_visitor(monkeypatch, user_key, path, label):
    registry = CollectorRegistry()
    request_metrics = prometheus.request_metrics
    monkeypatch.setattr(prometheus, "request_metrics", lambda server: request_metrics(server, registry=registry))
    monkeypatch.setattr("openlibrary.asgi_app.set_context_from_fastapi", lambda request: visitor.set(Visitor(user_key=user_key)))
    from openlibrary.asgi_app import create_app  # noqa: PLC0415

    app = create_app()

    @app.get("/librarian-page")
    def librarian_page():  # sync, so it runs in a worker thread, as is_librarian_or_higher() would mark the visitor
        visitor.get().is_librarian = True
        return {}

    with TestClient(app) as client:
        client.get(path)

    labels = {"handler": "none" if path == "/no-such-route" else path, "method": "GET", "server": "fastapi", "visitor": label}
    assert registry.get_sample_value("http_request_duration_seconds_count", labels) == 1
    status = "404" if path == "/no-such-route" else "200"
    assert registry.get_sample_value("http_requests_total", labels | {"status": status}) == 1
