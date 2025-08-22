import asyncio
from collections.abc import Callable
from typing import Any

# Create a persistent loop for WSGI
_persistent_loop = None


def run_sync(func: Callable[..., Any], *args, **kwargs) -> Any:
    """
    Run a function safely in both WSGI (sync) and ASGI (async) contexts.
    Keeps a persistent loop alive for WSGI so we don't hit 'Event loop is closed'.
    """
    global _persistent_loop

    result = func(*args, **kwargs)

    if asyncio.iscoroutine(result):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop running → WSGI context
            if _persistent_loop is None or _persistent_loop.is_closed():
                _persistent_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(_persistent_loop)
            return _persistent_loop.run_until_complete(result)
        else:
            # ASGI context (loop already running)
            return asyncio.run_coroutine_threadsafe(result, loop).result()

    # Sync function → return directly
    return result
