from __future__ import annotations


import time
from collections.abc import Awaitable, Callable


class MaxRetriesExceeded(Exception):
    last_exception: Exception

    def __init__(self, last_exception: Exception):
        self.last_exception = last_exception


class RetryStrategy:
    retry_count = 0
    last_exception: Exception | None = None

    def __init__(self, exceptions: list[type[Exception]], max_retries=3, delay=1):
        self.exceptions = exceptions
        self.max_retries = max_retries
        self.delay = delay

    def __call__[T](self, func: Callable[[], T]) -> T:
        try:
            return func()
        except Exception as e:
            if not any(isinstance(e, exc) for exc in self.exceptions):
                raise e

            self.last_exception = e

            if self.retry_count < self.max_retries:
                self.retry_count += 1
                time.sleep(self.delay)
                return self(func)
            else:
                raise MaxRetriesExceeded(self.last_exception)

    async def async_call[T](self, func: Callable[[], Awaitable[T]]) -> T:
        try:
            return await func()
        except Exception as e:
            if not any(isinstance(e, exc) for exc in self.exceptions):
                raise e

            self.last_exception = e

            if self.retry_count < self.max_retries:
                self.retry_count += 1
                await asyncio.sleep(self.delay)
                return await self.async_call(func)
            else:
                raise MaxRetriesExceeded(self.last_exception)
