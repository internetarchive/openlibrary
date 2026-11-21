"""Open Library's server-to-server client for the standalone iannotate
"snippets" service.

The service (ArchiveLabs/iannotate) runs as a single container on ol-home0 and
stores annotations/snippets; see ``docs/features/snippets.md``. Public read and
create are routed to it by the deployment edge, not by this app. This module
holds only the privileged paths Open Library makes itself, cross-host, the same
way it reaches the affiliate-server.

That is the image proxy's lookup (``list_snippets``) and the admin delete.
iannotate's ``DELETE /annotations`` takes ``?id=`` (unique row) or
``?annotation=`` (the annotation URL); it has no ``?uri=``, and a snippet's
``uri`` is not unique, so deletion is by the ``id`` returned from
``/api/snippets``.
"""

from __future__ import annotations

import logging

import httpx

from infogami import config

logger = logging.getLogger("openlibrary.snippets")

# iannotate is reached cross-host by FQDN, exactly like the affiliate-server
# (see docs/features/snippets.md). Overridable via the ``iannotate_url`` config
# key, but it defaults to the known host so no config change is required.
DEFAULT_IANNOTATE_URL = "http://ol-home0.us.archive.org:8000"

# Per-request timeout for the cross-host call, in seconds.
REQUEST_TIMEOUT = 10.0


def _iannotate_url() -> str:
    return config.get("iannotate_url") or DEFAULT_IANNOTATE_URL


def _async_client() -> httpx.AsyncClient:
    """The httpx client used for one call. Factored out so tests can swap in a
    ``MockTransport`` without reaching the network."""
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT)


async def delete_snippet(snippet_id: int) -> bool:
    """Delete one snippet from the iannotate service by its id.

    Makes the server-to-server ``DELETE /annotations?id=`` call (not a public
    route). Returns True when the service reports the row
    deleted, and False when it was already gone (404) or the service could not
    be reached — the caller decides what that means for the response.
    """
    url = f"{_iannotate_url()}/annotations"
    try:
        async with _async_client() as client:
            response = await client.delete(url, params={"id": snippet_id})
        response.raise_for_status()
        return bool(response.json().get("deleted"))
    except httpx.HTTPStatusError as error:
        # 404 is a benign "already gone / unknown id"; anything else is a fault
        # worth a traceback.
        if error.response.status_code != 404:
            logger.exception("iannotate delete failed for snippet id %s", snippet_id)
        return False
    except httpx.HTTPError:
        logger.exception("iannotate unreachable deleting snippet id %s", snippet_id)
        return False


async def list_snippets() -> list[dict] | None:
    """Every snippet in the iannotate service (it has no lookup by id), or None
    if the service could not be reached or returned something unusable."""
    url = f"{_iannotate_url()}/annotations"
    try:
        async with _async_client() as client:
            response = await client.get(url)
        response.raise_for_status()
        snippets = response.json()
    except httpx.HTTPError, ValueError:
        logger.exception("iannotate list failed")
        return None
    return snippets if isinstance(snippets, list) else None
