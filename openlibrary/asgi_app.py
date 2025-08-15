from __future__ import annotations

import logging
import os

import web  # type: ignore
import yaml  # type: ignore
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware

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
    # This serves our css/js files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # --- Fast routes (mounted within this app) ---
    @app.get("/_fast/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Mount authors router
    from openlibrary.fastapi.authors import router as authors_router  # type: ignore
    from openlibrary.fastapi.coauthors import router as coauthors_router  # type: ignore

    app.include_router(authors_router)
    app.include_router(coauthors_router)

    # Finally, mount the legacy app at "/" so all existing routes keep working.
    # Ordering matters: Fast routes are declared BEFORE the catch-all mount.
    app.mount("/", WSGIMiddleware(legacy_wsgi))

    return app


# The ASGI app instance Gunicorn/Uvicorn will serve
app = create_app()
