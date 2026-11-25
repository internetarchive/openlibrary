from typing import Annotated

import pytest
import yaml
from fastapi import APIRouter, Depends, FastAPI

from openlibrary.fastapi.shared.nonblocking import nonblocking
from scripts import generate_fastapi_routes
from scripts.generate_fastapi_routes import OUTPUT, REGENERATE, build_app, render_routes_yaml


def test_route_file_is_current():
    if OUTPUT.read_text() != render_routes_yaml(build_app()):
        pytest.fail(f"conf/k8s/fastapi-routes.yaml is stale. To update it, run:\n\n    {REGENERATE}\n", pytrace=False)


def test_fails_when_an_excluded_route_is_gone(monkeypatch):
    monkeypatch.setattr(generate_fastapi_routes, "EXCLUDED_PATHS", {"/no-such-route"})
    with pytest.raises(SystemExit, match="/no-such-route"):
        render_routes_yaml(build_app())


def _app_with(router: APIRouter) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)
    return app


@pytest.fixture
def no_exclusions(monkeypatch):
    monkeypatch.setattr(generate_fastapi_routes, "EXCLUDED_PATHS", set())
    monkeypatch.setattr(generate_fastapi_routes, "EXCLUDED_PREFIXES", ())


def test_routes_are_listed_under_their_group(no_exclusions):
    router = APIRouter()

    @router.get("/plain.json")
    async def plain():
        return {}

    @nonblocking
    @router.get("/fast.json")
    async def fast():
        return {}

    @router.get("/also-fast.json")
    @nonblocking
    async def also_fast():
        return {}

    groups = yaml.safe_load(render_routes_yaml(_app_with(router)))["fastapiRoutes"]
    assert groups == {"default": ["GET /plain.json"], "nonblocking": ["GET /also-fast.json", "GET /fast.json"]}


def test_empty_group_is_an_empty_list(no_exclusions):
    router = APIRouter()

    @router.get("/plain.json")
    def plain():
        return {}

    assert yaml.safe_load(render_routes_yaml(_app_with(router)))["fastapiRoutes"]["nonblocking"] == []


def test_nonblocking_rejects_a_sync_endpoint():
    def sync_endpoint():
        return {}

    with pytest.raises(TypeError, match="sync_endpoint"):
        nonblocking(sync_endpoint)


def test_nonblocking_rejects_sync_dependencies(no_exclusions):
    def blocking_dep():
        return 1

    async def async_dep(value: Annotated[int, Depends(blocking_dep)]):
        return value

    router = APIRouter()

    @router.get("/fast.json")
    @nonblocking
    async def fast(value: Annotated[int, Depends(async_dep)]):
        return {}

    with pytest.raises(SystemExit, match=r"/fast\.json.*blocking_dep"):
        render_routes_yaml(_app_with(router))


def test_webpy_health_check_stays_on_webpy():
    # HAProxy checks web.py on Kubernetes with /health/webpy, which only reaches web.py while FastAPI doesn't serve it.
    assert "/health/webpy" not in OUTPUT.read_text()
