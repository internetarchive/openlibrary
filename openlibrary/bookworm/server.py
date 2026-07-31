"""BookWorm FastAPI service (#12844).

Runs on ol-home0 (like the affiliate server). A background task polls every
registered feed on a timer — :func:`~openlibrary.bookworm.harvest.harvest_all`
fetches each feed and submits import records (carrying ``acquisitions[]``) to
Open Library's ``import_item`` queue, which ImportBot then loads. Exposes a
health check, a manual harvest trigger, and a feed listing.

Interval defaults to 5 minutes (``BOOKWORM_INTERVAL_SECONDS``) for testing; use
3600 in production. Point ``OL_CONFIG`` at the OL config so it reaches the db.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from openlibrary.bookworm import harvest
from openlibrary.bookworm.registry import FeedRegistry
from openlibrary.config import load_config

logger = logging.getLogger("openlibrary.bookworm.server")

HARVEST_INTERVAL_SECONDS = int(os.environ.get("BOOKWORM_INTERVAL_SECONDS", "300"))


def _load_config() -> None:
    load_config(os.environ.get("OL_CONFIG", "/openlibrary/conf/openlibrary.yml"))


async def _run_harvest() -> list[dict]:
    """Run one (synchronous) harvest cycle off the event loop."""
    return await asyncio.to_thread(harvest.harvest_all)


async def _harvest_loop() -> None:
    while True:
        try:
            logger.info("bookworm cycle: %s", await _run_harvest())
        except Exception:
            logger.exception("bookworm harvest cycle failed")
        await asyncio.sleep(HARVEST_INTERVAL_SECONDS)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        _load_config()
    except Exception:
        logger.exception("bookworm: load_config failed")
    task = asyncio.create_task(_harvest_loop())
    yield
    task.cancel()


app = FastAPI(title="OL BookWorm", lifespan=_lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "bookworm"})


@app.post("/harvest")
async def harvest_now() -> JSONResponse:
    """Trigger a harvest of all registered feeds immediately."""
    return JSONResponse({"results": await _run_harvest()})


@app.get("/feeds")
async def feeds() -> JSONResponse:
    return JSONResponse(
        [
            {
                "provider_name": feed.provider_name,
                "url": feed.url,
                "id_strategy": feed.id_strategy,
                "cursor_style": feed.cursor_style,
                "last_updated": str(feed.get("last_updated")),
            }
            for feed in FeedRegistry.all()
        ]
    )
