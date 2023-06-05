"""WSGI middleware used in Open Library.
"""
import web
from io import BytesIO
import gzip
from itertools import chain
from typing import Any, Callable, Dict, List, Union


class GZipMiddleware:
    """WSGI middleware to gzip the response."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    def __call__(
        self, environ: dict[str, Any], start_response: Callable
    ) -> Union[chain, list[bytes]]:
        accept_encoding = environ.get("HTTP_ACCEPT_ENCODING", "")
        if 'gzip' not in accept_encoding:
            return self.app(environ, start_response)

        response = web.storage(compress=False)

        def get_response_header(name, default=None):
            for hdr, value in response.headers:
                if hdr.lower() == name.lower():
                    return value
            return default

        def compress(text, level=9):
            f = BytesIO()
            gz = gzip.GzipFile(None, 'wb', level, fileobj=f)
            gz.write(text)
            gz.close()
            return f.getvalue()

        def new_start_response(status, headers):
            response.status = status
            response.headers = headers

            if status.startswith("200") and get_response_header(
                "Content-Type", ""
            ).startswith("text/"):
                headers.append(("Content-Encoding", "gzip"))
                headers.append(("Vary", "Accept-Encoding"))
                response.compress = True
            return start_response(status, headers)

        data = self.app(environ, new_start_response)
        if response.compress:
            return [compress(b"".join(data), 9)]
        else:
            return data
