"""FastAPI dependencies for Open Library.

This module holds small, well-documented dependencies that are explicit and
local by design. They are not promoted to global ContextVars until a
cross-cutting need emerges.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request  # runtime dependency for FastAPI injection

from openlibrary.utils.request_context import req_context


def get_fullpath(request: Request) -> str:
    """Return the request fullpath (path + query string).

    FastAPI equivalent of ``web.ctx.fullpath`` which is set in
    ``openlibrary/core/processors/readableurls.py:55`` as
    ``web.ctx.path + web.ctx.query``. Unlike ``str(request.url)``, this does
    not include scheme or netloc.

    Examples:
        - ``/account/loans`` -> ``/account/loans``
        - ``/search?q=python&page=2`` -> ``/search?q=python&page=2``
        - ``/books/OL1M/edit?mode=borrow`` -> ``/books/OL1M/edit?mode=borrow``

    Use as a dependency where a redirect target or canonical path is needed:

        .. code-block:: python

            from typing import Annotated
            from fastapi import Depends
            from openlibrary.fastapi.shared.dependencies import get_fullpath

            @router.get("/some/path")
            async def handler(fullpath: Annotated[str, Depends(get_fullpath)]):
                ...

    This is intentionally not exposed as a global/ContextVar yet — keep usage
    explicit and local until a cross-cutting need emerges.
    """
    return request.url.path + (f"?{request.url.query}" if request.url.query else "")


def get_client_ip() -> str:
    """Return the client IP for the current request.

    Uses the first entry of X-Forwarded-For when present, falling back to
    the loopback address (e.g. for internal or test requests).
    """
    x_fwd = req_context.get().x_forwarded_for
    return x_fwd.split(",")[0].strip() if x_fwd else "127.0.0.1"


ClientIpDep = Annotated[str, Depends(get_client_ip)]
