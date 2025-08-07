from __future__ import annotations

import logging
import os

# FastAPI/Starlette
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from starlette.middleware.wsgi import WSGIMiddleware
except ImportError as e:
    raise RuntimeError(
        "FastAPI is not installed in the runtime environment. "
        "Ensure fastapi and uvicorn are available in your Docker image."
    ) from e

# Legacy stack
import web  # type: ignore
import yaml  # type: ignore

logger = logging.getLogger("openlibrary.asgi_app")


# ---- Legacy loader (mirrors scripts/openlibrary-server) --------------------


def _setup_env() -> None:
    os.environ.setdefault("PYTHON_EGG_CACHE", "/tmp/.python-eggs")
    os.environ.setdefault("REAL_SCRIPT_NAME", "")


def _https_middleware(app):
    def wrapper(environ, start_response):
        if environ.get("HTTP_X_SCHEME") == "https":
            environ["wsgi.url_scheme"] = "https"
        return app(environ, start_response)

    return wrapper


def _load_legacy_wsgi(ol_config_file: str):
    """Create the legacy WSGI application exactly like scripts/openlibrary-server.

    Returns a WSGI callable suitable for wrapping with WSGIMiddleware.
    """
    import infogami  # type: ignore
    from infogami import config  # type: ignore

    # match scripts/openlibrary-server behavior
    from infogami.utils import delegate as _delegate  # noqa: F401 - side-effects

    config.plugin_path += ["openlibrary.plugins"]
    config.site = "openlibrary.org"

    infogami.load_config(ol_config_file)

    # Configure infobase from YAML reference in openlibrary.yml
    if config.get("infobase_config_file"):
        base_dir = os.path.dirname(ol_config_file)
        path = os.path.join(base_dir, config.infobase_config_file)
        with open(path) as f:
            config.infobase = yaml.safe_load(f)

    config.middleware.append(_https_middleware)

    # Finish infogami setup and build WSGI app with middleware + static handler
    infogami._setup()
    wsgi_app = _get_wsgi_app()
    wsgi_app = web.httpserver.StaticMiddleware(wsgi_app)
    return wsgi_app


def _get_wsgi_app():
    from infogami import config  # type: ignore
    from infogami.utils import delegate  # type: ignore

    return delegate.app.wsgifunc(*config.middleware)


# ---- FastAPI app -----------------------------------------------------------


def create_app() -> FastAPI:
    _setup_env()

    ol_config = os.environ.get("OL_CONFIG", "/openlibrary/conf/openlibrary.yml")
    try:
        legacy_wsgi = _load_legacy_wsgi(ol_config)
    except Exception:
        logger.exception("Failed to initialize legacy WSGI app")
        raise

    app = FastAPI(title="OpenLibrary ASGI", version="1.0")

    # --- Fast routes (mounted within this app) ---
    @app.get("/_fast/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/_fast/authors/coauthors{olid}")
    def author_coauthors(olid: str):
        """Return author basic info and co-authors via Solr aggregation.

        This is intentionally JSON-first for an initial endpoint. We can add an
        HTML template later.
        """
        try:
            data = _compute_author_network(olid)
            return JSONResponse(data)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("error in author network endpoint for %s", olid)
            raise HTTPException(status_code=500, detail=str(e))

    # Finally, mount the legacy app at "/" so all existing routes keep working.
    # Ordering matters: Fast routes are declared BEFORE the catch-all mount.
    app.mount("/", WSGIMiddleware(legacy_wsgi))

    return app


def _compute_author_network(olid: str) -> dict:
    """Compute co-authors by querying Solr and author details via JSON API.

    - Fetch author details from the classic JSON API: /authors/{olid}.json
    - Query Solr for works with author_key:OL... and aggregate other authors.
    """
    import requests  # type: ignore

    # Resolve service URLs from env with sensible defaults for docker-compose
    base_web = os.environ.get("OL_WEB_INTERNAL", "http://localhost:8080")
    solr_url = os.environ.get("SOLR_URL", "http://solr:8983/solr/openlibrary/select")

    # Query Solr for works by this author and compute co-authors
    params = {
        "q": f"author_key:{olid}",
        "fl": "key,title,author_key,author_name",
        "rows": 2000,
        "wt": "json",
    }
    s_resp = requests.get(solr_url, params=params, timeout=15)
    s_resp.raise_for_status()
    docs = s_resp.json().get("response", {}).get("docs", [])

    if not docs:
        raise HTTPException(
            status_code=404, detail="author not found or no works in index"
        )

    # Derive canonical author name from docs where this olid appears
    name_counts: dict[str, int] = {}
    for d in docs:
        keys: list[str] = d.get("author_key", []) or []
        names: list[str] = d.get("author_name", []) or []
        for i, k in enumerate(keys):
            if k == olid:
                nm = names[i] if i < len(names) else None
                if nm:
                    name_counts[nm] = name_counts.get(nm, 0) + 1

    author_name = max(name_counts, key=name_counts.get) if name_counts else None

    # Aggregate co-authors
    counts: dict[str, dict[str, object]] = {}
    for d in docs:
        keys: list[str] = d.get("author_key", []) or []
        names: list[str] = d.get("author_name", []) or []
        # zip may drop if lengths differ; use index lookup
        name_by_key = {
            k: names[i] if i < len(names) else None for i, k in enumerate(keys)
        }
        for k in keys:
            if k == olid:
                continue
            if k not in counts:
                counts[k] = {
                    "key": f"/authors/{k}",
                    "olid": k,
                    "name": name_by_key.get(k),
                    "shared_works": 0,
                }
            counts[k]["shared_works"] = int(counts[k]["shared_works"]) + 1

    coauthors = sorted(counts.values(), key=lambda x: -int(x["shared_works"]))

    return {
        "author": {"key": f"/authors/{olid}", "olid": olid, "name": author_name},
        "co_authors": coauthors,
        "stats": {"works_considered": len(docs), "unique_coauthors": len(coauthors)},
    }


# The ASGI app instance Gunicorn/Uvicorn will serve
app = create_app()
