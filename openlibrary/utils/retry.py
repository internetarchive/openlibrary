import time
from typing import Optional


class MaxRetriesExceeded(Exception):
    last_exception: Exception

    def __init__(self, last_exception: Exception):
        self.last_exception = last_exception


class RetryStrategy:
    retry_count = 0
    last_exception: Optional[Exception] = None

    def __init__(self, exceptions: list[type[Exception]], max_retries=3, delay=1):
        self.exceptions = exceptions
        self.max_retries = max_retries
        self.delay = delay

    def __call__(self, func):
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
