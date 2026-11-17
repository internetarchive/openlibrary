import pytest

from scripts import generate_fastapi_routes
from scripts.generate_fastapi_routes import OUTPUT, REGENERATE, build_app, render_routes_yaml


def test_route_file_is_current():
    if OUTPUT.read_text() != render_routes_yaml(build_app()):
        pytest.fail(f"conf/k8s/fastapi-routes.yaml is stale. To update it, run:\n\n    {REGENERATE}\n", pytrace=False)


def test_fails_when_an_excluded_route_is_gone(monkeypatch):
    monkeypatch.setattr(generate_fastapi_routes, "EXCLUDED_PATHS", {"/no-such-route"})
    with pytest.raises(SystemExit, match="/no-such-route"):
        render_routes_yaml(build_app())
