#!/bin/sh
# Start mailpit in the background (SMTP :1025, web :8025)
mailpit --smtp 0.0.0.0:1025 --listen 0.0.0.0:8025 &

# Start the FastAPI mock service
exec uvicorn main:app --host 0.0.0.0 --port 8090
