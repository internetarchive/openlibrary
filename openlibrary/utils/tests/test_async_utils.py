import asyncio
import contextvars

import pytest

from openlibrary.utils.async_utils import AsyncBridge


def test_run_from_sync_succeeds():
    b = AsyncBridge()
    assert b.run(asyncio.sleep(0, result=42)) == 42


def test_wrap_preserves_name_and_doc():
    b = AsyncBridge()

    async def foo():
        """doc"""

    assert b.wrap(foo).__name__ == "foo"
    assert b.wrap(foo).__doc__ == "doc"
    assert b.wrap(foo, name="bar").__name__ == "bar"


def test_reentrancy_raises():
    b = AsyncBridge()

    async def outer():
        with pytest.raises(RuntimeError, match="deadlock"):
            b.run(asyncio.sleep(0))

    b.run(outer())


def test_nested_wrap_raises():
    b = AsyncBridge()

    async def inner():
        return 1

    wrapped = b.wrap(inner)

    async def outer():
        with pytest.raises(RuntimeError, match="deadlock"):
            wrapped()

    b.run(outer())


def test_contextvar_propagation():
    b = AsyncBridge()
    var = contextvars.ContextVar("test_var")

    async def inner():
        return var.get()

    var.set("expected")
    assert b.run(inner()) == "expected"


def test_normal_wrap_still_works():
    b = AsyncBridge()

    async def add(a, b_):
        return a + b_

    wrapped = b.wrap(add)
    assert wrapped(2, 3) == 5
    assert wrapped(a=10, b_=20) == 30
