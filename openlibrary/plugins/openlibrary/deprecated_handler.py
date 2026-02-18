"""Handler for deprecated web.py endpoints.

Redirects deprecated endpoints to port 18080 in dev environment,
or raises a loud error in production.
This is temporary while we migrate to fastapi and have two containers running.
"""

import web

import infogami
from infogami.utils import delegate


def handle_deprecated_request():
    """Handle the deprecated endpoint request."""
    # Check if we're in dev environment
    is_dev = 'dev' in infogami.config.features

    if is_dev:
        # Simple string replacement to redirect to port 18080
        new_url = web.ctx.home.replace(':8080', ':18080') + web.ctx.fullpath
        raise web.seeother(new_url)
    else:
        # Raise a loud error in production
        error_msg = f'DEPRECATED ENDPOINT ACCESSED: {web.ctx.path}. This endpoint has been migrated to FastAPI and should not be accessed in production.'
        raise web.internalerror(error_msg)


class DeprecatedEndpointHandler(delegate.page):
    """Catches all deprecated endpoints and redirects them."""

    encoding = 'json'

    def GET(self):
        return handle_deprecated_request()

    def POST(self):
        return handle_deprecated_request()


# List of deprecated paths (all json)
DEPRECATED_PATHS = [
    '/search',
    '/search/lists',
    '/search/subjects',
    '/search/authors',
    '/search/inside',
    '/languages',
    '/reading-goal',
]
