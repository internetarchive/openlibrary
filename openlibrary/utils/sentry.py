import logging
import re
from dataclasses import dataclass

import sentry_sdk
import web
from sentry_sdk.tracing import TRANSACTION_SOURCE_ROUTE, Transaction
from sentry_sdk.utils import capture_internal_exceptions

from infogami.utils.app import (
    find_page,
    modes,
)
from infogami.utils.types import type_patterns
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
            # Don't forward cookies to Sentry
            if k == 'HTTP_COOKIE':
                continue
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
            traces_sample_rate=self.config.get('traces_sample_rate', 0.0),
            profiles_sample_rate=self.config.get('profiles_sample_rate', 0.0),
            release=get_software_version(),
        )

    def bind_to_webpy_app(self, app: web.application) -> None:
        _internalerror = app.internalerror

        def capture_exception():
            self.capture_exception_webpy()
            return _internalerror()

        app.internalerror = capture_exception
        app.add_processor(WebPySentryProcessor(app))

    def capture_exception_webpy(self):
        with sentry_sdk.push_scope() as scope:
            scope.add_event_processor(add_web_ctx_to_event)
            sentry_sdk.capture_exception()

    def capture_exception(self, ex):
        with sentry_sdk.push_scope() as scope:
            scope.add_event_processor(add_web_ctx_to_event)
            sentry_sdk.capture_exception(ex)


@dataclass
class InfogamiRoute:
    route: str
    mode: str = 'view'
    encoding: str | None = None

    def to_sentry_name(self) -> str:
        return (
            self.route
            + (f'.{self.encoding}' if self.encoding else '')
            + (f'?m={self.mode}' if self.mode != 'view' else '')
        )


class WebPySentryProcessor:
    def __init__(self, app: web.application):
        self.app = app

    def find_route_name(self) -> str:
        handler, groups = self.app._match(self.app.mapping, web.ctx.path)
        web.debug('ROUTE HANDLER', handler, groups)
        return handler or '<other>'

    def __call__(self, handler):
        route_name = self.find_route_name()
        hub = sentry_sdk.Hub.current
        with sentry_sdk.Hub(hub) as hub:
            with hub.configure_scope() as scope:
                scope.clear_breadcrumbs()
                scope.add_event_processor(add_web_ctx_to_event)

            environ = dict(web.ctx.env)
            # Don't forward cookies to Sentry
            if 'HTTP_COOKIE' in environ:
                del environ['HTTP_COOKIE']

            transaction = Transaction.continue_from_environ(
                environ,
                op="http.server",
                name=route_name,
                source=TRANSACTION_SOURCE_ROUTE,
            )

            with hub.start_transaction(transaction):
                try:
                    return handler()
                finally:
                    transaction.set_http_status(int(web.ctx.status.split()[0]))


class InfogamiSentryProcessor(WebPySentryProcessor):
    """
    Processor to profile the webpage and send a transaction to Sentry.
    """

    def find_route_name(self) -> str:
        def find_type() -> tuple[str, str] | None:
            return next(
                (
                    (pattern, typename)
                    for pattern, typename in type_patterns.items()
                    if re.search(pattern, web.ctx.path)
                ),
                None,
            )

        def find_route() -> InfogamiRoute:
            result = InfogamiRoute('<other>')

            cls, args = find_page()
            if cls:
                if hasattr(cls, 'path'):
                    result.route = cls.path
                else:
                    result.route = web.ctx.path
            elif type_page := find_type():
                result.route = type_page[0]

            if web.ctx.get('encoding'):
                result.encoding = web.ctx.encoding

            requested_mode = web.input(_method='GET').get('m', 'view')
            if requested_mode in modes:
                result.mode = requested_mode

            return result

        return find_route().to_sentry_name()
