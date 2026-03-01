from __future__ import annotations

import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk import set_tag
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import infogami
from openlibrary.utils.request_context import set_context_from_fastapi
from openlibrary.utils.sentry import Sentry, init_sentry

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


def _load_legacy_wsgi():
    """Initialize legacy configuration and side-effects as in scripts/openlibrary-server.

    This function does not return a WSGI callable; it is called for its side effects only.
    """
    import infogami  # type: ignore
    from infogami import config  # type: ignore

    # match scripts/openlibrary-server behavior
    from infogami.utils import delegate as _delegate  # noqa: F401 - side-effects

    ol_config_path = Path(__file__).parent / "conf" / "openlibrary.yml"
    ol_config_file = os.environ.get("OL_CONFIG", str(ol_config_path))

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


def setup_i18n(app: FastAPI):
    """Sets up i18n middleware for FastAPI to set request.state.lang based on language preferences.
    Keep in sync with
    https://github.com/internetarchive/infogami/blob/58be1edd4cd2c834cf8272993f377afd4777ed8b/infogami/utils/i18n.py#L130-L164
    """

    def parse_lang_header(request: Request) -> str | None:
        """Parses HTTP Accept-Language header."""
        accept_language = request.headers.get("accept-language", "")
        if not accept_language:
            return None

        # Split by comma and optional whitespace
        re_accept_language = re.compile(r",\s*")
        tokens = re_accept_language.split(accept_language)

        # Take just the language part (e.g., 'en' from 'en-gb;q=0.8')
        langs = [t[:2] for t in tokens if t and not t.startswith("*")]
        return langs[0] if langs else None

    def parse_lang_cookie(request: Request) -> str | None:
        """Parses HTTP_LANG cookie."""
        return request.cookies.get("HTTP_LANG")

    def parse_query_string(request: Request) -> str | None:
        """Parses lang query parameter."""
        return request.query_params.get("lang")

    @app.middleware("http")
    async def i18n_middleware(request: Request, call_next):
        """Middleware to set request.state.lang based on language preferences."""
        lang = parse_query_string(request) or parse_lang_cookie(request) or parse_lang_header(request) or None
        request.state.lang = lang

        response = await call_next(request)
        return response


def setup_debugpy():
    import debugpy  # noqa: T100

    # Start listening for debugger connections
    debugpy.listen(("0.0.0.0", 3000))  # noqa: T100
    logger.info("🐛 Debugger ready to attach from VS Code! Select 'OL: Attach to FastAPI Container'.")


sentry: Sentry | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    if os.environ.get("LOCAL_DEV", "false").lower() == "true":
        setup_debugpy()
    yield
    # Shutdown (if needed in the future)


def create_app() -> FastAPI | None:
    if "pytest" not in sys.modules:
        _setup_env()

        if os.environ.get("CI"):
            import pytest

            pytest.skip("Skipping in CI", allow_module_level=True)

        try:
            # We still call this even though we don't use it because of the side effects
            _load_legacy_wsgi()

            global sentry
            if sentry is not None:
                return None
            sentry = init_sentry(getattr(infogami.config, "sentry", {}))
            set_tag("fastapi", True)

        except Exception:
            logger.exception("Failed to initialize legacy WSGI app")
            raise

    app = FastAPI(
        title="OpenLibrary ASGI",
        version="0.0.1",
        debug=os.environ.get("LOCAL_DEV", "false").lower() == "true",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=False,  # We don't want to allow cookies because then we have to limit origins.
        allow_methods=["GET", "OPTIONS"],
        max_age=3600 * 24,  # Cache preflight response for 24 hours
        # Keep in sync with
        # https://github.com/internetarchive/openlibrary/blob/1606a0d27d16f1fe64991884002a86d3597d9ecb/openlibrary/plugins/openlibrary/processors.py#L70-L89
    )

    # Needed for the staging nginx proxy
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    @app.middleware("http")
    async def add_fastapi_header(request: Request, call_next):
        """Middleware to add a header indicating the response came from FastAPI."""
        response = await call_next(request)
        response.headers["X-Served-By"] = "FastAPI"
        return response

    # Add prometheus metrics
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, include_in_schema=False)

    @app.middleware("http")
    async def set_context(request: Request, call_next):
        set_context_from_fastapi(request)
        response = await call_next(request)
        return response

    # setup_i18n is below set_context so that it can use the request.state.lang in set_context
    # because the handlers are called in reverse order
    setup_i18n(app)

    # --- Fast routes (mounted within this app) ---
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    from openlibrary.fastapi.account import router as account_router
    from openlibrary.fastapi.cdn import router as cdn_router
    from openlibrary.fastapi.internal.api import router as internal_router
    from openlibrary.fastapi.languages import router as languages_router
    from openlibrary.fastapi.partials import router as partials_router
    from openlibrary.fastapi.public_my_books import router as public_my_books_router
    from openlibrary.fastapi.publishers import router as publishers_router
    from openlibrary.fastapi.search import router as search_router
    from openlibrary.fastapi.subjects import router as subjects_router
    from openlibrary.fastapi.yearly_reading_goals import (
        router as yearly_reading_goals_router,
    )

    # Include routers
    app.include_router(cdn_router)
    app.include_router(public_my_books_router)
    app.include_router(languages_router)
    app.include_router(partials_router)
    app.include_router(publishers_router)
    app.include_router(search_router)
    app.include_router(subjects_router)
    app.include_router(account_router)
    app.include_router(yearly_reading_goals_router)
    app.include_router(internal_router)

    return app


# The ASGI app instance Gunicorn/Uvicorn will serve
app = create_app()
