import web

from openlibrary.contribute import save
from openlibrary.plugins.openlibrary import contribute


class FakeUser:
    key = "/people/reader"


def test_member_skips_intro_after_clicking_through_or_saving_a_task(monkeypatch):
    monkeypatch.setattr(save, "recent_saves", lambda key, limit=5: [])
    monkeypatch.setattr(web, "cookies", dict)
    assert not contribute.has_seen_intro(FakeUser())

    monkeypatch.setattr(web, "cookies", lambda: {contribute.INTRO_COOKIE: "1"})
    assert contribute.has_seen_intro(FakeUser())

    monkeypatch.setattr(web, "cookies", dict)
    monkeypatch.setattr(save, "recent_saves", lambda key, limit=5: [object()])
    assert contribute.has_seen_intro(FakeUser())


def test_member_cta_goes_to_a_task_and_dismisses_the_intro():
    cta = contribute.build_cta(FakeUser())
    assert cta["href"] == "/tasks/one"
    assert [link["href"] for link in cta["secondary"]] == ["/tasks"]
    assert cta["intro"] == {"cookie": contribute.INTRO_COOKIE, "days": contribute.INTRO_COOKIE_DAYS}


def test_visitor_cta_asks_for_an_account_and_never_sets_the_cookie():
    cta = contribute.build_cta(None)
    assert cta["href"].startswith("/account/create")
    assert cta["intro"] is None
