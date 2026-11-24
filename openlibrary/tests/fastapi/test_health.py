from unittest.mock import patch


def test_health_does_not_use_the_threadpool(fastapi_client):
    """The readiness probe must answer even when every threadpool worker is busy with slow sync handlers."""

    def no_threadpool(*args, **kwargs):
        raise AssertionError("/health ran in the threadpool")

    with patch("fastapi.routing.run_in_threadpool", no_threadpool):
        resp = fastapi_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
