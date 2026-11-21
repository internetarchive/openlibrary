"""FastAPI endpoints for the /snippets feature.

The /snippets *page* is served by web.py (``templates/snippets.html`` +
``js/snippets.js``), and public read/create are routed to the iannotate service
at the deployment edge. This router adds only the one privileged action: a
super-librarian deleting a shared snippet (e.g. spam).

In production HAProxy routes ``DELETE /snippets/{id}`` here (its
``is_fastapi_path`` matches ``snippets/[0-9]+``) while the ``GET /snippets``
page stays on web.py.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from openlibrary.core.snippets import delete_snippet

# Must stay a runtime import: FastAPI resolves the Depends from this annotation,
# so moving it into a TYPE_CHECKING block would silently disable the auth gate.
from openlibrary.fastapi.auth import SuperLibrarianDep  # noqa: TC001

router = APIRouter(tags=["snippets"], include_in_schema=False)


@router.delete("/snippets/{snippet_id}")
async def delete_snippet_route(snippet_id: int, _: SuperLibrarianDep) -> dict:
    """Delete one shared snippet by its id.

    Restricted to admins/super-librarians (``SuperLibrarianDep``). The deletion
    is made server-to-server against the iannotate service. Returns 404 when the
    snippet was already gone or the service could not be reached.
    """
    if not await delete_snippet(snippet_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snippet not found or could not be deleted",
        )
    return {"deleted": True, "id": snippet_id}
