"""Internal helpers shared by the shell context builders."""

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def _safe[T](fn: Callable[[], T], default: T) -> T:
    """Execute a function and return its result, falling back to default on any failure.

    Swallowing the exception keeps one broken extractor from taking down the
    shell, but a fallback must never be silent: in normal operation these
    extractions succeed, so a failure means something is genuinely wrong and
    the header/head will degrade (a missing badge, a blank analytics
    dimension). Log it so the degradation is diagnosable.
    """
    try:
        val = fn()
        return default if val is None else val
    except Exception:
        logger.warning("shell context extraction failed", exc_info=True)
        return default
