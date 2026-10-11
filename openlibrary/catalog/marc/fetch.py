"""Bounded HTTP range fetch for MARC source files.

Context: internetarchive/openlibrary#13874 — ``show-records`` pages for huge
MARC files (e.g. Harvard dumps) time out. One contributor is unbounded
buffering: when the server does not honor ``Range`` and answers ``200`` with
the whole file, ``response.content`` loads gigabytes into the worker.

``fetch_range`` streams and never buffers more than ``size`` bytes, and
retries timeouts instead of failing on the first slow first-byte.
"""

from __future__ import annotations

import requests

CHUNK = 16384


class MarcFetchError(Exception):
    """Base error for MARC fetches."""


class MarcFetchTimeout(MarcFetchError):
    """Raised when every attempt times out."""


def fetch_range(
    url: str,
    offset: int,
    size: int,
    timeout: int = 3,
    retries: int = 1,
) -> tuple[int, bytes]:
    """GET up to ``size`` bytes at ``offset``; returns ``(status_code, data)``.

    The ``Range`` end is inclusive (as in the original call site), then the
    result is capped, so at most ``size`` bytes are ever buffered, even if
    the server ignores ``Range`` and answers ``200``. Raises
    :class:`MarcFetchTimeout` when all ``1 + retries`` attempts time out;
    other ``requests`` exceptions (e.g. ``HTTPError`` from ``raise_for_status``)
    propagate unchanged.
    """
    headers = {"Range": "bytes=%d-%d" % (offset, offset + size)}
    attempts = 1 + max(retries, 0)
    for _ in range(attempts):
        try:
            with requests.get(url, headers=headers, timeout=timeout, stream=True) as response:
                response.raise_for_status()
                buf = bytearray()
                for chunk in response.iter_content(CHUNK):
                    buf += chunk
                    if len(buf) >= size:
                        break
                return response.status_code, bytes(buf[:size])
        except requests.Timeout:
            continue
    raise MarcFetchTimeout(f"timed out after {attempts} attempts: {url}")
