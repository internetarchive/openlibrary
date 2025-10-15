from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

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
    """Initialize legacy configuration and side-effects as in scripts/openlibrary-server.

    This function does not return a WSGI callable; it is called for its side effects only.
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
        # TODO: fix the types here
        path = os.path.join(base_dir, config.infobase_config_file)  # type: ignore[attr-defined]
        with open(path) as f:
            config.infobase = yaml.safe_load(f)  # type: ignore[attr-defined]

    config.middleware.append(_https_middleware)

    # Finish infogami setup and build WSGI app with middleware + static handler
    infogami._setup()


# ---- FastAPI app -----------------------------------------------------------


def create_app() -> FastAPI:
    _setup_env()

    if os.environ.get("CI"):
        pytest.skip("Skipping in CI", allow_module_level=True)

    ol_config_path = Path(__file__).parent / "conf" / "openlibrary.yml"
    ol_config = os.environ.get("OL_CONFIG", str(ol_config_path))
    try:
        # We still call this even though we don't use it because of the side effects
        legacy_wsgi = _load_legacy_wsgi(ol_config)  # noqa: F841
    except Exception:
        logger.exception("Failed to initialize legacy WSGI app")
        raise

    app = FastAPI(title="OpenLibrary ASGI", version="0.0.1")

    # Needed for the staging nginx proxy
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    # --- Fast routes (mounted within this app) ---
    @app.get("/_fast/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    from openlibrary.fastapi.search import router as search_router  # type: ignore

    app.include_router(search_router)

    return app


# The ASGI app instance Gunicorn/Uvicorn will serve
app = create_app()
