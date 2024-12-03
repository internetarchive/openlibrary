"""Generic web.py application processors.
"""

import time

import web

__all__ = ["RateLimitProcessor"]


class RateLimitProcessor:
    """Application processor to ratelimit the access per ip."""

    def __init__(
        self, limit: int, window_size: int = 600, path_regex: str = "/.*"
    ) -> None:
        """Creates a rate-limit processor to limit the number of
        requests/ip in the time frame.

        :param int limit: the maximum number of requests allowed in the given time window.
        :param int window_size: the time frame in seconds during which the requests are measured.
        :param int path_regex: regular expression to specify which urls are rate-limited.
        """
        self.path_regex = web.re_compile(path_regex)
        self.limit = limit
        self.window_size = window_size
        self.reset(None)

    def reset(self, timestamp):
        self.window = {}
        self.window_timestamp = timestamp

    def get_window(self):
        t = int(time.time() / self.window_size)
        if t != self.window_timestamp:
            self.reset(t)
        return self.window

    def check_rate(self):
        """Returns True if access rate for the current IP address is
        less than the allowed limit.
        """
        window = self.get_window()
        ip = web.ctx.ip

        if window.get(ip, 0) < self.limit:
            window[ip] = 1 + window.get(ip, 0)
            return True
        else:
            return False

    def __call__(self, handler):
        if self.path_regex.match(web.ctx.path):
            if self.check_rate():
                return handler()
            else:
                raise web.HTTPError("503 Service Unavailable")
