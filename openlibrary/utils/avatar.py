"""Local-dev avatar file helpers.

In LOCAL_DEV the avatar upload endpoint cannot write to archive.org (there
are no real S3 credentials), so instead of pretending the upload landed on
the Internet Archive the sanitized bytes are stored under ``var/avatars/``
(gitignored) and the ``/people/{username}/avatar`` route serves them directly
instead of redirecting to archive.org. This keeps the whole avatar flow —
upload, preview, refresh, remove — working in local development.

These helpers are only ever called when ``get_ol_env().LOCAL_DEV`` (or fake
``mock_`` test keys) is in play; production never touches these files.
"""

import contextlib
from pathlib import Path

_AVATAR_DIR = Path("var/avatars")


def local_avatar_path(username: str) -> Path:
    return _AVATAR_DIR / f"{username}.jpg"


def read_local_avatar(username: str) -> bytes | None:
    """Return the locally stored avatar bytes, or None when absent."""
    try:
        return local_avatar_path(username).read_bytes()
    except OSError:
        return None


def write_local_avatar(username: str, contents: bytes) -> None:
    path = local_avatar_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)


def delete_local_avatar(username: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        local_avatar_path(username).unlink()
