from openlibrary.core import lending


class TestAddAvailability:
    def test_reads_ocaids(self, monkeypatch):
        def mock_get_availability_of_ocaids(ocaids):
            return {'foo': {'status': 'available'}}
        monkeypatch.setattr(lending, "get_availability_of_ocaids", mock_get_availability_of_ocaids)

        f = lending.add_availability
        assert f([{'ocaid': 'foo'}]) == [{'ocaid': 'foo', 'availability': {'status': 'available'}}]
        assert f([{'identifier': 'foo'}]) == [{'identifier': 'foo', 'availability': {'status': 'available'}}]
        assert f([{'ia': 'foo'}]) == [{'ia': 'foo', 'availability': {'status': 'available'}}]
        assert f([{'ia': ['foo']}]) == [{'ia': ['foo'], 'availability': {'status': 'available'}}]

    def test_handles_ocaid_none(self):
        f = lending.add_availability
        assert f([{}]) == [{'availability': {'status': 'error'}}]

    def test_handles_availability_none(self, monkeypatch):
        def mock_get_availability_of_ocaids(ocaids):
            return {'foo': None}
        monkeypatch.setattr(lending, "get_availability_of_ocaids", mock_get_availability_of_ocaids)

        f = lending.add_availability
        assert f([{'ocaid': 'foo'}]) == [{'ocaid': 'foo', 'availability': {'status': 'error'}}]