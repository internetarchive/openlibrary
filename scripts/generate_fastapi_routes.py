"""Write the routes, per method, that go to FastAPI rather than web.py (see #14384).

conf/k8s/fastapi-routes.yaml is for the Kubernetes gateway. Kubernetes deploys read it, so its path and the `fastapiRoutes` keys
are a contract with the ol-web Helm chart. Its routes are grouped: `nonblocking` for routes marked @nonblocking
(openlibrary/fastapi/shared/nonblocking.py), which Kubernetes can serve from pods tuned for that, and `default` for the rest.

HAPROXY_EXACT and HAPROXY_REGEX hold the same routes as HAProxy pattern files, which the production HAProxy loads (see olsystem's
etc/haproxy/haproxy.cfg) to split traffic between web.py and FastAPI on the VMs the same way.

openlibrary/tests/fastapi/test_fastapi_routes.py fails while a file is stale and prints REGENERATE, the command that rewrites it.
"""

from __future__ import annotations

import inspect
import re
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
CONF = Path(__file__).resolve().parent.parent / "conf"
OUTPUT = CONF / "k8s" / "fastapi-routes.yaml"
# compose.production.yaml mounts this directory into web_haproxy, and olsystem's haproxy.cfg loads the files by name.
HAPROXY_EXACT = CONF / "haproxy" / "fastapi-routes-exact.txt"
HAPROXY_REGEX = CONF / "haproxy" / "fastapi-routes-regex.txt"

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

type RouteGroups = dict[str, tuple[dict[str, set[str]], dict[str, set[str]]]]


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


def collect_routes(app: FastAPI) -> RouteGroups:
    """The routes to send to FastAPI: group -> (pages, api), each mapping a path to its methods."""
    groups: RouteGroups = {group: ({}, {}) for group in GROUPS}
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
    return groups


def render_routes_yaml(app: FastAPI) -> str:
    groups = collect_routes(app)

    def entries(group: dict[str, set[str]]) -> list[str]:
        return [f"    - {' '.join(sorted(methods))} {path}" for path, methods in sorted(group.items())]

    lines = [
        "# Generated by scripts/generate_fastapi_routes.py. Do not edit by hand.",
        f"# Regenerate: {REGENERATE}",
        "fastapiRoutes:",
    ]
    for group_name, (pages, api) in groups.items():
        if not pages and not api:
            lines.append(f"  {group_name}: []")
            continue
        lines.append(f"  {group_name}:")
        if pages:
            lines += ["    # Pages (SitePageRoute)", *entries(pages)]
        if api:
            lines += ["    # JSON / API", *entries(api)]
    return "\n".join([*lines, ""])


def haproxy_path_regex(path: str) -> str:
    """The regex, unanchored, that the ol-web Helm chart's HTTPRoutes use for a path with parameters.

    As in FastAPI, {name} matches one path segment and {name:path} the rest.
    """
    regex = ""
    for part in re.split(r"(\{[^}]+\})", path):
        if part.startswith("{"):
            regex += ".+" if part.endswith(":path}") else "[^/]+"
        else:
            regex += re.sub(r"([.+?^$()|*\[\]\\])", r"\\\1", part)
    return regex


def render_haproxy_patterns(app: FastAPI) -> dict[Path, str]:
    """The HAProxy pattern files: one "METHOD /path" per line, for the method and path pairs that go to FastAPI rather than web.py.

    HAPROXY_EXACT is matched as strings and HAPROXY_REGEX as regexes. HEAD isn't listed (see collect_routes), so as on
    Kubernetes, HEAD requests go to web.py.
    """
    exact, regex = [], []
    for pages, api in collect_routes(app).values():
        for path, methods in [*pages.items(), *api.items()]:
            for method in methods:
                if "{" in path:
                    regex.append(f"^{method} {haproxy_path_regex(path)}$")
                else:
                    exact.append(f"{method} {path}")
    header = [
        "# Generated by scripts/generate_fastapi_routes.py. Do not edit by hand.",
        f"# Regenerate: {REGENERATE}",
        "# HAProxy pattern file: the method and path pairs to send to FastAPI, matched against the request's method and path.",
    ]
    return {HAPROXY_EXACT: "\n".join([*header, *sorted(exact), ""]), HAPROXY_REGEX: "\n".join([*header, *sorted(regex), ""])}


def render_all(app: FastAPI) -> dict[Path, str]:
    return {OUTPUT: render_routes_yaml(app), **render_haproxy_patterns(app)}


def build_app() -> FastAPI:
    app = create_app()
    assert app is not None
    return app


if __name__ == "__main__":
    for path, text in render_all(build_app()).items():
        path.write_text(text)
        print(f"Wrote {path}")
