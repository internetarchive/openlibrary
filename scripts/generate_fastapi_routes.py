"""Write conf/k8s/fastapi-routes.yaml: the routes, per method, that the Kubernetes gateway sends to FastAPI (see #14384).

Routes marked @nonblocking (openlibrary/fastapi/shared/nonblocking.py) are listed under `fastapiNonblockingRoutes`, which
Kubernetes can serve from pods tuned for them, and the rest under `fastapiRoutes`. Kubernetes deploys read this file, so
its path and both keys are a contract with the ol-web Helm chart.

openlibrary/tests/fastapi/test_fastapi_routes.py fails while the file is stale and prints REGENERATE, the command that rewrites it.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest  # noqa: F401 - create_app() skips the legacy web.py setup under pytest, so this runs without its config
from fastapi.routing import APIRoute, iter_route_contexts

from openlibrary.asgi_app import create_app
from openlibrary.fastapi.shared.nonblocking import DEFAULT, GROUPS, NONBLOCKING, route_group
from openlibrary.fastapi.shared.site_page import SitePageRoute

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.dependencies.models import Dependant  # codespell:ignore

REGENERATE = "uv run --with-requirements requirements_test.txt python -m scripts.generate_fastapi_routes"
OUTPUT = Path(__file__).resolve().parent.parent / "conf" / "k8s" / "fastapi-routes.yaml"

# Routes FastAPI serves that the gateway must not send to it. An explicit list, because route metadata can't decide it:
# real public routes are include_in_schema=False (/api/books) or tagged internal (/search/facets.json).
# Each must still exist, so the list can't rot. The /static mount has no methods, so it is never listed.
EXCLUDED_PATHS = {
    "/metrics",  # Prometheus internals
    "/account/test.json",
    "/account/protected.json",
    "/account/optional.json",
}
EXCLUDED_PREFIXES = ("/status/",)  # testing dashboard
CATCH_ALL = "/{path:path}"  # the local dev / testing proxy to web.py; only registered there


def _is_async(call: Any) -> bool:
    if inspect.iscoroutinefunction(call) or inspect.isasyncgenfunction(call):
        return True
    # A dependency can be a class instance whose __call__ is the dependency (e.g. fastapi.security classes).
    dunder_call = getattr(call, "__call__", None)  # noqa: B004 - checking how it is called, not whether it is callable
    return not inspect.isfunction(call) and not inspect.isclass(call) and dunder_call is not None and inspect.iscoroutinefunction(dunder_call)


def _sync_dependencies(dependant: Dependant) -> list[str]:  # codespell:ignore
    """Names of the dependencies (at any depth) that FastAPI would run in its thread pool."""
    found = []
    for dep in dependant.dependencies:  # codespell:ignore
        if dep.call is not None and not _is_async(dep.call):
            found.append(getattr(dep.call, "__qualname__", repr(dep.call)))
        found += _sync_dependencies(dep)
    return found


def render_routes_yaml(app: FastAPI) -> str:
    # group -> (pages, api), each path -> methods
    groups: dict[str, tuple[dict[str, set[str]], dict[str, set[str]]]] = {group: ({}, {}) for group in GROUPS}
    problems = []
    for route in iter_route_contexts(app.routes):
        if route.path is None or route.methods is None:
            continue
        if route.path in EXCLUDED_PATHS or route.path == CATCH_ALL or route.path.startswith(EXCLUDED_PREFIXES):
            continue
        api_route = route.original_route
        group_name = route_group(api_route.endpoint) if isinstance(api_route, APIRoute) else DEFAULT
        if group_name == NONBLOCKING and isinstance(api_route, APIRoute) and (sync := _sync_dependencies(api_route.dependant)):  # codespell:ignore
            problems.append(f"{route.path} is marked @nonblocking but has sync dependencies, which run in a thread pool (see nonblocking.py): {', '.join(sync)}")
        pages, api = groups[group_name]
        group = pages if isinstance(api_route, SitePageRoute) else api
        group.setdefault(route.path, set()).update(route.methods - {"HEAD"})
    if problems:
        raise SystemExit("\n".join(problems))

    paths = {route.path for route in iter_route_contexts(app.routes)}
    if missing := sorted(EXCLUDED_PATHS - paths) + [p for p in EXCLUDED_PREFIXES if not any(str(path).startswith(p) for path in paths)]:
        raise SystemExit(f"Excluded routes no longer exist: {', '.join(missing)}. Update scripts/generate_fastapi_routes.py.")

    def entries(group: dict[str, set[str]]) -> list[str]:
        return [f"  - {' '.join(sorted(methods))} {path}" for path, methods in sorted(group.items())]

    def section(key: str, group_name: str) -> list[str]:
        pages, api = groups[group_name]
        if not pages and not api:
            return [f"{key}: []"]
        lines = [f"{key}:"]
        if pages:
            lines += ["  # Pages (SitePageRoute)", *entries(pages)]
        if api:
            lines += ["  # JSON / API", *entries(api)]
        return lines

    return "\n".join(
        [
            "# Generated by scripts/generate_fastapi_routes.py. Do not edit by hand.",
            f"# Regenerate: {REGENERATE}",
            *section("fastapiRoutes", DEFAULT),
            *section("fastapiNonblockingRoutes", NONBLOCKING),
            "",
        ]
    )


def build_app() -> FastAPI:
    app = create_app()
    assert app is not None
    return app


if __name__ == "__main__":
    OUTPUT.write_text(render_routes_yaml(build_app()))
    print(f"Wrote {OUTPUT}")
