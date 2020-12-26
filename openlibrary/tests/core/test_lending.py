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
        assert f([{}]) == [{}]

    def test_handles_availability_none(self, monkeypatch):
        def mock_get_availability_of_ocaids(ocaids):
            return {'foo': {'status': 'error'}}
        monkeypatch.setattr(lending, "get_availability_of_ocaids", mock_get_availability_of_ocaids)

        f = lending.add_availability
        r = f([{'ocaid': 'foo'}])
        print(r)
        assert r[0]['availability']['status'] == 'error'
