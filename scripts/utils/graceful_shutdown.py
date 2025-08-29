import signal

# Global flag indicating whether a shutdown signal has been received.
_shutdown_requested = False


def _shutdown_handler(signum, frame):
    """
    Signal handler that sets the global `_stop_requested` flag to True
    when a termination signal is received.

    Args:
        signum (int): The signal number received (e.g., SIGINT or SIGTERM).
        frame (frame object): The current stack frame (not used).
    """
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[graceful_shutdown] Received shutdown signal, stopping...")


def was_shutdown_requested() -> bool:
    """
    Checks whether a shutdown has been requested via a captured system signal.

    Returns:
        bool: True if a SIGINT or SIGTERM has been received and shutdown was requested;
              False otherwise.
    """
    return _shutdown_requested


def init_signal_handler():
    """
    Initializes signal handlers for graceful shutdown on SIGINT and SIGTERM.

    Registers the given handler function to respond to:
      - SIGINT (triggered by Ctrl-C)
      - SIGTERM (triggered by kill or system shutdown)

    This function should be called once at the start of your script.
    """

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)
