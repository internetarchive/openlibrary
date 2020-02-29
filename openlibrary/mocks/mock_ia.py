"""Mock of openlibrary.core.ia module.
"""
import pytest
from openlibrary.core import ia

@pytest.fixture
def mock_ia(request, monkeypatch):
    """pytest funcarg to mock openlibrary.core.ia module.

        from openlibrary.core import ia

        def test_ia(mock_ia):
            assert ia.get_metadata("foo") == {}

            mock_ia.set_metadata("foo", {"collection": ["a", "b"]})
            assert ia.get_metadata("foo") == {"collection": ["a", "b"]}
    """
    metadata = {}

    class IA:
        def set_metadata(self, itemid, meta):
            metadata[itemid] = meta

        def get_metadata(self, itemid):
            return metadata.get(itemid, {})

    mock_ia = IA()
    monkeypatch.setattr(ia, 'get_metadata', ia.get_metadata)

    return mock_ia
