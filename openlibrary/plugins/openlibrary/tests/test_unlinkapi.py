import json
from unittest.mock import MagicMock, patch

import web

from openlibrary.plugins.openlibrary.api import unlink_ia_ol


def mock_web_input_func(data):
    def _mock_web_input(*args, **kwargs):
        return web.storage(kwargs | data)

    return _mock_web_input


class FakeEdition:
    def __init__(self, data):
        self.key = data.get("key", "/books/OL1M")
        self._data = data

    def dict(self):
        return dict(self._data)


def test_make_dark_default_op_uses_dark_comment():
    """Omitting op keeps existing behavior: the "dark" comment."""
    edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123"]})

    with (
        patch("openlibrary.plugins.openlibrary.api.accounts.RunAs"),
        patch("web.ctx") as mock_web_ctx,
    ):
        mock_web_ctx.ip = "127.0.0.1"
        mock_web_ctx.site = MagicMock()

        unlink_ia_ol.make_dark(edition, "foo123")

        comment = mock_web_ctx.site.save.call_args[0][1]
        assert comment == "Unlink OCAID: Item no longer available"


def test_make_dark_op_dark_uses_dark_comment():
    edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123"]})

    with (
        patch("openlibrary.plugins.openlibrary.api.accounts.RunAs"),
        patch("web.ctx") as mock_web_ctx,
    ):
        mock_web_ctx.ip = "127.0.0.1"
        mock_web_ctx.site = MagicMock()

        unlink_ia_ol.make_dark(edition, "foo123", op="dark")

        comment = mock_web_ctx.site.save.call_args[0][1]
        assert comment == "Unlink OCAID: Item no longer available"


def test_make_dark_op_mismatch_uses_mismatch_comment():
    edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123"]})

    with (
        patch("openlibrary.plugins.openlibrary.api.accounts.RunAs"),
        patch("web.ctx") as mock_web_ctx,
    ):
        mock_web_ctx.ip = "127.0.0.1"
        mock_web_ctx.site = MagicMock()

        unlink_ia_ol.make_dark(edition, "foo123", op="mismatch")

        comment = mock_web_ctx.site.save.call_args[0][1]
        assert comment == "Unlink OCAID: Wrong Item"


def test_make_dark_unknown_op_falls_back_to_dark_comment():
    """An unrecognized op doesn't 400 -- it falls back to the dark comment."""
    edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123"]})

    with (
        patch("openlibrary.plugins.openlibrary.api.accounts.RunAs"),
        patch("web.ctx") as mock_web_ctx,
    ):
        mock_web_ctx.ip = "127.0.0.1"
        mock_web_ctx.site = MagicMock()

        unlink_ia_ol.make_dark(edition, "foo123", op="bogus")

        comment = mock_web_ctx.site.save.call_args[0][1]
        assert comment == "Unlink OCAID: Item no longer available"


def test_make_dark_still_strips_ocaid_and_source_record():
    """The op param only changes the comment -- the edit itself is unchanged."""
    edition = FakeEdition({"key": "/books/OL1M", "ocaid": "foo123", "source_records": ["ia:foo123", "other:xyz"]})

    with (
        patch("openlibrary.plugins.openlibrary.api.accounts.RunAs"),
        patch("web.ctx") as mock_web_ctx,
    ):
        mock_web_ctx.ip = "127.0.0.1"
        mock_web_ctx.site = MagicMock()

        unlink_ia_ol.make_dark(edition, "foo123", op="mismatch")

        data = mock_web_ctx.site.save.call_args[0][0]
        assert "ocaid" not in data
        assert data["source_records"] == ["other:xyz"]


def test_post_passes_op_query_param_through_to_make_dark():
    """/api/unlink threads the op web.input param through to make_dark."""
    with (
        patch("web.input") as mock_web_input,
        patch("openlibrary.plugins.openlibrary.api.HMACToken.verify") as mock_verify,
        patch("openlibrary.plugins.openlibrary.api.unlink_ia_ol.make_dark") as mock_make_dark,
        patch("web.ctx") as mock_web_ctx,
    ):
        mock_web_input.side_effect = mock_web_input_func({"digest": "abc", "msg": "foo123|123456", "op": "mismatch"})
        mock_verify.return_value = True
        mock_web_ctx.site = MagicMock()
        mock_web_ctx.site.things.side_effect = [["/books/OL1M"], []]
        mock_web_ctx.site.get.return_value = FakeEdition({"key": "/books/OL1M"})

        result = json.loads(unlink_ia_ol().POST()["rawtext"])

        assert result == {"status": "ok"}
        mock_make_dark.assert_called_once_with(mock_web_ctx.site.get.return_value, "foo123", "mismatch")


def test_post_default_op_is_dark():
    """Omitting op on the request still calls make_dark with the "dark" default."""
    with (
        patch("web.input") as mock_web_input,
        patch("openlibrary.plugins.openlibrary.api.HMACToken.verify") as mock_verify,
        patch("openlibrary.plugins.openlibrary.api.unlink_ia_ol.make_dark") as mock_make_dark,
        patch("web.ctx") as mock_web_ctx,
    ):
        mock_web_input.side_effect = mock_web_input_func({"digest": "abc", "msg": "foo123|123456"})
        mock_verify.return_value = True
        mock_web_ctx.site = MagicMock()
        mock_web_ctx.site.things.side_effect = [["/books/OL1M"], []]
        mock_web_ctx.site.get.return_value = FakeEdition({"key": "/books/OL1M"})

        json.loads(unlink_ia_ol().POST()["rawtext"])

        mock_make_dark.assert_called_once_with(mock_web_ctx.site.get.return_value, "foo123", "dark")
