from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from openlibrary.utils import prometheus


def test_metrics_are_labelled_fastapi(monkeypatch):
    # Its own registry: other apps' tests (e.g. coverstore's) register the same metrics in the default one
    registry = CollectorRegistry()
    request_metrics = prometheus.request_metrics
    monkeypatch.setattr(prometheus, "request_metrics", lambda server: request_metrics(server, registry=registry))
    monkeypatch.setattr("openlibrary.asgi_app.set_context_from_fastapi", lambda request: None)
    from openlibrary.asgi_app import create_app  # noqa: PLC0415

    with TestClient(create_app()) as client:
        client.get("/no-such-route")

    labels = {"handler": "none", "method": "GET", "server": "fastapi", "status": "404"}
    assert registry.get_sample_value("http_requests_total", labels) == 1
