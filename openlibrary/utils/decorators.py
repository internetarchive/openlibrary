from functools import wraps

import web

from openlibrary.accounts import get_current_user


def authorized_for(*expected_args):
    """Check for membership in any given usergroup before proceeding."""

    def decorator_authorized(func):
        @wraps(func)
        def wrapper_authorized(*args, **kwargs):
            user = get_current_user()
            if not user:
                raise web.unauthorized(message='Requires log-in.')

            authorized = False
            for usergroup in expected_args:
                if user.is_usergroup_member(usergroup):
                    authorized = True

            if not authorized:
                # Throw some authorization error
                raise web.forbidden(message='Requires elevated permissions.')
            return func(*args, *kwargs)

        return wrapper_authorized

    return decorator_authorized
