#!/bin/sh
# Start mailpit in the background (SMTP :1025, web :8025)
mailpit --smtp 0.0.0.0:1025 --listen 0.0.0.0:8025 &

# Start the FastAPI mock service.
#
# --reload picks up edits to the bind-mounted /app (see compose.override.yaml)
# without a container restart. Force polling: the mount is a host bind mount, and
# inotify events do not cross it on macOS, so the default watcher would never
# fire there.
exec env WATCHFILES_FORCE_POLLING=true \
    uvicorn main:app --host 0.0.0.0 --port 8090 --reload --reload-dir /app
