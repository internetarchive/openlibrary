"""
HTTP utilities for Open Library.

Provides a default timeout constant to prevent outbound requests from
blocking workers indefinitely when upstream services hang or respond slowly.
"""

# Default timeout (in seconds) for all outbound HTTP requests.
# Using a tuple (connect_timeout, read_timeout) is recommended by the
# requests library: https://requests.readthedocs.io/en/latest/user/advanced/#timeouts
OL_REQUEST_TIMEOUT = (10, 30)
