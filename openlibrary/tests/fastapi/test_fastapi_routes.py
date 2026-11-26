import re
from typing import Annotated

import pytest
import yaml
from fastapi import APIRouter, Depends, FastAPI

from openlibrary.fastapi.shared.nonblocking import nonblocking
from scripts import generate_fastapi_routes
from scripts.generate_fastapi_routes import (
    CONF,
    HAPROXY_EXACT,
    HAPROXY_REGEX,
    REGENERATE,
    build_app,
    haproxy_path_regex,
    render_all,
    render_haproxy_patterns,
    render_routes_yaml,
)


def test_route_files_are_current():
    if stale := [str(path.relative_to(CONF.parent)) for path, text in render_all(build_app()).items() if not path.exists() or path.read_text() != text]:
        pytest.fail(f"Stale route files: {', '.join(stale)}. To update them, run:\n\n    {REGENERATE}\n", pytrace=False)


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
    assert not any("/health/webpy" in text for text in render_all(build_app()).values())


@pytest.mark.parametrize(
    ("path", "matches", "misses"),
    [
        ("/works/OL{work_id}W/notes.json", ["/works/OL1W/notes.json"], ["/works/OL1W/notes", "/works/OL1W/notesXjson", "/works/a/OL1W/notes.json"]),
        ("/subjects/{key:path}.json", ["/subjects/love.json", "/subjects/place:paris/x.json"], ["/subjects/.json", "/subjects/love"]),
        ("/cdn/archive.org/{filename}", ["/cdn/archive.org/a.js"], ["/cdn/archiveXorg/a.js", "/cdn/archive.org/a/b.js"]),
    ],
)
def test_haproxy_path_regex(path, matches, misses):
    regex = haproxy_path_regex(path)
    assert all(re.fullmatch(regex, p) for p in matches)
    assert not any(re.fullmatch(regex, p) for p in misses)


def test_haproxy_patterns_match_by_method(no_exclusions):
    router = APIRouter()

    @router.get("/page")
    @router.post("/page")
    async def page():
        return {}

    @router.delete("/items/{item_id}")
    async def delete_item(item_id: str):
        return {}

    def entries(text):
        return [line for line in text.split("\n") if line and not line.startswith("#")]

    patterns = render_haproxy_patterns(_app_with(router))
    assert entries(patterns[HAPROXY_EXACT]) == ["GET /page", "POST /page"]
    assert entries(patterns[HAPROXY_REGEX]) == ["^DELETE /items/[^/]+$"]


def test_haproxy_patterns_skip_excluded_routes():
    assert "/metrics" not in render_haproxy_patterns(build_app())[HAPROXY_EXACT]
