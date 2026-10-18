import web

from openlibrary.utils import sentry


def test_find_infogami_route_uses_registered_path_and_request_format(monkeypatch):
    class WorksPage:
        path = r"^/works/[^/]*$"

    monkeypatch.setattr(sentry, "find_page", lambda: (WorksPage, []))
    monkeypatch.setattr(sentry.web, "ctx", web.storage(path="/works/OL1W", encoding="json"))
    monkeypatch.setattr(sentry.web, "input", lambda **_kwargs: {"m": "history"})
    monkeypatch.setattr(sentry, "modes", {"history": {}})

    route = sentry.find_infogami_route()

    assert route.route == r"^/works/[^/]*$"
    assert route.encoding == "json"
    assert route.mode == "history"


def test_find_infogami_route_uses_class_name_when_page_has_no_path(monkeypatch):
    class DynamicPage:
        pass

    monkeypatch.setattr(sentry, "find_page", lambda: (DynamicPage, []))
    monkeypatch.setattr(sentry.web, "ctx", web.storage(path="/dynamic/value"))
    monkeypatch.setattr(sentry.web, "input", lambda **_kwargs: {})
    monkeypatch.setattr(sentry, "modes", {})

    route = sentry.find_infogami_route()

    assert route.route == "/DynamicPage"
    assert route.mode == "view"


def test_infogami_sentry_processor_uses_shared_route_lookup(monkeypatch):
    route = sentry.InfogamiRoute("^/authors/[^/]*$", encoding="json")
    monkeypatch.setattr(sentry, "find_infogami_route", lambda: route)

    processor = sentry.InfogamiSentryProcessor(None)

    assert processor.find_route_name() == "^/authors/[^/]*$.json"
