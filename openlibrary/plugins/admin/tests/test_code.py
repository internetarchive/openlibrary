from typing import cast
from openlibrary.accounts.model import (
    OpenLibraryAccount,
)
from openlibrary.plugins.admin.code import revert_all_user_edits
import web

from openlibrary.plugins.upstream.models import (
    Changeset,  # noqa: F401 side effects may be needed
)


def make_test_account(username: str) -> OpenLibraryAccount:
    web.ctx.site.register(
        username=username,
        email=f"{username}@foo.org",
        password="password",
        displayname=f"{username} User",
    )
    web.ctx.site.activate_account(username)
    return cast(OpenLibraryAccount, OpenLibraryAccount.get(username=username))


def make_thing(key: str, title: str = '', thing_type: str | None = None) -> dict:
    if thing_type == '/type/delete':
        return {
            "key": key,
            "type": {"key": "/type/delete"},
        }
    if key.startswith("/works/"):
        return {
            "key": key,
            "type": {"key": "/type/work"},
            "title": title,
        }
    elif '/lists/' in key:
        return {
            "key": key,
            "type": {"key": "/type/list"},
            "name": title,
        }
    else:
        raise NotImplementedError(
            f"make_thing not implemented for {key} or {thing_type}"
        )


class TestRevertAllUserEdits:
    def test_no_edits(self, mock_site):
        alice = make_test_account("alice")

        revert_all_user_edits(alice)

    def test_deletes_spam_works(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL123W", "Good Book Title"),
            action='add-book',
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL789W", "Spammy New Book"),
            action='add-book',
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL345W", "Spammy New Book 2"),
            action='add-book',
        )
        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL12333W", "Good Book Title 2"),
            action='add-book',
        )

        revert_all_user_edits(spam_alice)

        # Good books un-altered
        assert web.ctx.site.get("/works/OL123W").revision == 1
        assert web.ctx.site.get("/works/OL123W").title == "Good Book Title"
        assert web.ctx.site.get("/works/OL12333W").revision == 1
        assert web.ctx.site.get("/works/OL12333W").title == "Good Book Title 2"

        # Spam books deleted
        assert web.ctx.site.get("/works/OL789W").revision == 2
        assert web.ctx.site.get("/works/OL789W").type.key == "/type/delete"
        assert web.ctx.site.get("/works/OL345W").revision == 2
        assert web.ctx.site.get("/works/OL345W").type.key == "/type/delete"

    def test_reverts_spam_edits(self, mock_site):
        good_alice = make_test_account("good_alice")
        spam_alice = make_test_account("spam_alice")

        web.ctx.site.save(
            author=good_alice.get_user(),
            query=make_thing("/works/OL123W", "Good Book Title"),
            action='add-book',
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL123W", "Spammy Book Title"),
            action='edit-book',
        )

        revert_all_user_edits(spam_alice)

        # Reverted back to good edit
        assert web.ctx.site.get("/works/OL123W").revision == 3
        assert web.ctx.site.get("/works/OL123W").title == "Good Book Title"
        assert web.ctx.site.get("/works/OL123W").type.key == "/type/work"

    def test_does_not_undelete(self, mock_site):
        spam_alice = make_test_account("spam_alice")

        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/people/spam_alice/lists/OL123L", "spam spam spam"),
            action='lists',
        )
        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing(
                "/people/spam_alice/lists/OL123L", thing_type='/type/delete'
            ),
            action='lists',
        )

        revert_all_user_edits(spam_alice)

        assert web.ctx.site.get("/people/spam_alice/lists/OL123L").revision == 2
        assert (
            web.ctx.site.get("/people/spam_alice/lists/OL123L").type.key
            == "/type/delete"
        )

    def test_two_spammy_editors(self, mock_site):
        spam_alice = make_test_account("spam_alice")
        spam_bob = make_test_account("spam_bob")

        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL1W", "Alice is Awesome"),
            action='add-book',
        )
        web.ctx.site.save(
            author=spam_bob.get_user(),
            query=make_thing("/works/OL2W", "Bob is Awesome"),
            action='add-book',
        )

        web.ctx.site.save(
            author=spam_alice.get_user(),
            query=make_thing("/works/OL2W", "Bob Sucks"),
            action='edit-book',
        )
        web.ctx.site.save(
            author=spam_bob.get_user(),
            query=make_thing("/works/OL1W", "Alice Sucks"),
            action='edit-book',
        )

        revert_all_user_edits(spam_alice)

        # Reverted back to good edit
        assert web.ctx.site.get("/works/OL1W").revision == 3
        assert web.ctx.site.get("/works/OL1W").type.key == "/type/delete"
        assert web.ctx.site.get("/works/OL2W").revision == 3
        assert web.ctx.site.get("/works/OL2W").title == "Bob is Awesome"

        revert_all_user_edits(spam_bob)

        # Reverted back to good edit
        assert web.ctx.site.get("/works/OL1W").revision == 3
        assert web.ctx.site.get("/works/OL1W").type.key == "/type/delete"
        assert web.ctx.site.get("/works/OL2W").revision == 4
        assert web.ctx.site.get("/works/OL2W").type.key == "/type/delete"
