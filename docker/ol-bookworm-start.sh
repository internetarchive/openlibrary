#!/bin/bash
# BookWorm feed-ingestion FastAPI service (#12844). Runs on ol-home0 like the
# affiliate server. Polls registered feeds on a timer and submits import records
# (with acquisitions) to Open Library's import_item queue.
python --version
exec uvicorn openlibrary.bookworm.server:app --host 0.0.0.0 --port "${BOOKWORM_PORT:-8140}"
