from contextvars import ContextVar
from typing import Any

import web

# ContextVar to store the context dictionary for the current execution context
_fast_ctx_var: ContextVar[dict[str, Any] | None] = ContextVar('fast_ctx', default=None)


class FastContext:
    """
    A context object that is intended to be used in both web.py and FastAPI.
    It uses ContextVars to maintain its own storage, making it safe for
    both threads and async tasks.

    If an attribute is missing, it checks web.ctx and raises an error if found there
    to encourage migration.
    """

    def _get_storage(self) -> dict[str, Any]:
        """Returns the dictionary stored in the current context."""
        return _fast_ctx_var.get() or {}

    def __getattr__(self, name: str) -> Any:
        if name in (storage := self._get_storage()):
            return storage[name]

        if hasattr(web, 'ctx'):
            found = False
            val = None
            try:
                if name in web.ctx:
                    found = True
                    val = web.ctx[name]
                elif hasattr(web.ctx, name):
                    found = True
                    val = getattr(web.ctx, name)
            except (AttributeError, KeyError, TypeError):
                pass

            if found:
                raise AttributeError(
                    f"Attribute '{name}' not found in fast_ctx, but found in web.ctx with value {val!r}. "
                    f"Please implement this directly in FastContext."
                )

        raise AttributeError(f"Attribute '{name}' not found in fast_ctx")

    def __setattr__(self, name: str, value: Any) -> None:
        # We must use __dict__ for internal attributes if we had any,
        # but we don't have any instance attributes other than what's in ContextVar.
        storage = self._get_storage()
        # Since ContextVars are immutable-ish (you should set the whole object),
        # but we are storing a mutable dict, this works.
        # However, for true safety in async, we might want to set a new dict.
        # But for the use-case of request-local storage, mutating the dict is standard.
        if not storage and _fast_ctx_var.get() is storage:
            # Ensure we have a fresh dict if it was the default empty one
            storage = {}
            _fast_ctx_var.set(storage)

        storage[name] = value

    def __getitem__(self, name: str) -> Any:
        if name in (storage := self._get_storage()):
            return storage[name]

        if hasattr(web, 'ctx'):
            try:
                if name in web.ctx:
                    val = web.ctx[name]
                    raise KeyError(
                        f"Key '{name}' not found in fast_ctx, but found in web.ctx with value {val!r}. "
                        f"Please implement this directly in FastContext."
                    )
            except KeyError:
                raise
            except (AttributeError, TypeError):
                pass

        raise KeyError(name)

    def __setitem__(self, name: str, value: Any) -> None:
        storage = self._get_storage()
        if not storage and _fast_ctx_var.get() is storage:
            storage = {}
            _fast_ctx_var.set(storage)
        storage[name] = value

    def get(self, name: str, default: Any = None) -> Any:
        if name in (storage := self._get_storage()):
            return storage[name]

        if hasattr(web, 'ctx'):
            found = False
            val = None
            try:
                if name in web.ctx:
                    found = True
                    val = web.ctx[name]
                elif hasattr(web.ctx, name):
                    found = True
                    val = getattr(web.ctx, name)
            except (AttributeError, KeyError, TypeError):
                pass

            if found:
                raise AttributeError(
                    f"Key/Attribute '{name}' not found in fast_ctx, but found in web.ctx with value {val!r}. "
                    f"Please implement this directly in FastContext."
                )

        return default

    def setdefault(self, name: str, default: Any = None) -> Any:
        storage = self._get_storage()
        if not storage and _fast_ctx_var.get() is storage:
            storage = {}
            _fast_ctx_var.set(storage)
        return storage.setdefault(name, default)

    def __contains__(self, name: str) -> bool:
        return name in self._get_storage()

    def clear(self):
        """Reset the context variable for the current context."""
        _fast_ctx_var.set({})


fast_ctx = FastContext()
