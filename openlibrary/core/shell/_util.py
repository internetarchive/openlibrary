"""Internal helpers shared by the shell context builders."""

from collections.abc import Callable


def _safe[T](fn: Callable[[], T], default: T) -> T:
    """Execute a function and return its result, falling back to default on any failure."""
    try:
        val = fn()
        return default if val is None else val
    except Exception:  # noqa: BLE001
        return default
