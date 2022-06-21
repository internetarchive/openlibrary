import logging

import sentry_sdk
import web
from sentry_sdk.utils import capture_internal_exceptions

from openlibrary.utils import get_software_version


def header_name_from_env(env_name: str) -> str:
    """
    Convert an env name as stored in web.ctx.env to a "normal"
    header name

    >>> header_name_from_env('HTTP_FOO_BAR')
    'foo-bar'
    >>> header_name_from_env('CONTENT_LENGTH')
    'content-length'
    """
    header_name = env_name
    if env_name.startswith('HTTP_'):
        header_name = env_name[5:]
    return header_name.lower().replace('_', '-')


def add_web_ctx_to_event(event: dict, hint: dict) -> dict:
    if not web.ctx:
        return event

    with capture_internal_exceptions():
        request_info = event.setdefault("request", {})

        headers = {}
        env = {}
        for k, v in web.ctx.env.items():
            if k.startswith('HTTP_') or k in ('CONTENT_LENGTH', 'CONTENT_TYPE'):
                headers[header_name_from_env(k)] = v
            else:
                env[k] = v

        request_info["url"] = web.ctx.home + web.ctx.fullpath
        request_info["headers"] = headers
        request_info["env"] = env
        request_info["method"] = web.ctx.method
    return event


class Sentry:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.enabled = bool(config.get('enabled'))
        self.logger = logging.getLogger("sentry")
        self.logger.info(f"Setting up sentry (enabled={self.enabled})")

    def init(self):
        sentry_sdk.init(
            dsn=self.config['dsn'],
            environment=self.config['environment'],
            release=get_software_version(),
        )

    def bind_to_webpy_app(self, app: web.application) -> None:
        _internalerror = app.internalerror

        def capture_exception():
            self.capture_exception_webpy()
            return _internalerror()

        app.internalerror = capture_exception

    def capture_exception_webpy(self):
        with sentry_sdk.push_scope() as scope:
            scope.add_event_processor(add_web_ctx_to_event)
            sentry_sdk.capture_exception()
