from unittest.mock import Mock, patch

from openlibrary.core import lending


class TestAddAvailability:
    def test_reads_ocaids(self, monkeypatch):
        def mock_get_availability_of_ocaids(ocaids):
            return {'foo': {'status': 'available'}}

        monkeypatch.setattr(
            lending, "get_availability_of_ocaids", mock_get_availability_of_ocaids
        )

        f = lending.add_availability
        assert f([{'ocaid': 'foo'}]) == [
            {'ocaid': 'foo', 'availability': {'status': 'available'}}
        ]
        assert f([{'identifier': 'foo'}]) == [
            {'identifier': 'foo', 'availability': {'status': 'available'}}
        ]
        assert f([{'ia': 'foo'}]) == [
            {'ia': 'foo', 'availability': {'status': 'available'}}
        ]
        assert f([{'ia': ['foo']}]) == [
            {'ia': ['foo'], 'availability': {'status': 'available'}}
        ]

    def test_handles_ocaid_none(self):
        f = lending.add_availability
        assert f([{}]) == [{}]

    def test_handles_availability_none(self, monkeypatch):
        def mock_get_availability_of_ocaids(ocaids):
            return {'foo': {'status': 'error'}}

        monkeypatch.setattr(
            lending, "get_availability_of_ocaids", mock_get_availability_of_ocaids
        )

        f = lending.add_availability
        r = f([{'ocaid': 'foo'}])
        print(r)
        assert r[0]['availability']['status'] == 'error'


class TestGetAvailability:
    def test_cache(self):
        with patch("openlibrary.core.lending.requests.get") as mock_get:
            mock_get.return_value = Mock()
            mock_get.return_value.json.return_value = {
                "responses": {"foo": {"status": "open"}}
            }

            foo_expected = {
                "status": "open",
                "identifier": "foo",
                "is_restricted": False,
                "is_browseable": False,
                "__src__": 'core.models.lending.get_availability',
            }
            bar_expected = {
                "status": "error",
                "identifier": "bar",
                "is_restricted": True,
                "is_browseable": False,
                "__src__": 'core.models.lending.get_availability',
            }

            r = lending.get_availability("identifier", ["foo"])
            assert mock_get.call_count == 1
            assert r == {"foo": foo_expected}

            # Should not make a call to the API again
            r2 = lending.get_availability("identifier", ["foo"])
            assert mock_get.call_count == 1
            assert r2 == {"foo": foo_expected}

            # Now should make a call for just the new identifier
            mock_get.return_value.json.return_value = {
                "responses": {"bar": {"status": "error"}}
            }
            r3 = lending.get_availability("identifier", ["foo", "bar"])
            assert mock_get.call_count == 2
            assert mock_get.call_args[1]['params']['identifier'] == "bar"
            assert r3 == {"foo": foo_expected, "bar": bar_expected}
