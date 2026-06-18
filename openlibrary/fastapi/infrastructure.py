"""
FastAPI endpoints for infrastructure and utility paths.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Request

import infogami

router = APIRouter()


@router.get("/robots.txt")
async def get_robots_txt(request: Request) -> str:
    """
    Serve robots.txt based on environment.

    In development (dev in features or non-openlibrary.org host), serves norobots.txt.
    In production, serves robots.txt.

    Returns:
        str: Content of robots.txt or norobots.txt with text/plain content type
    """
    is_dev = "dev" in infogami.config.features or request.headers.get("host", "").split(":")[0] != "openlibrary.org"

    robots_file = "norobots.txt" if is_dev else "robots.txt"

    static_dir = Path(__file__).parent.parent.parent / "static"
    robots_path = static_dir / robots_file

    # Use asyncio.to_thread to avoid blocking the event loop with file I/O
    content = await asyncio.to_thread(robots_path.read_text)

    return content
