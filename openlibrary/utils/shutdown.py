"""Utility to setup graceful shutdown for a process. This enables docker to shutdown faster rather than waiting 10 seconds."""

import signal
import sys


def setup_graceful_shutdown():
    def shutdown_handler(signum, frame):
        print("Shutting down")
        sys.exit(0)

    # catch SIGINT and SIGTERM to allow graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
