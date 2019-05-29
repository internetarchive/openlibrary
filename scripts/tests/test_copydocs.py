from ..copydocs import copy, KeyVersionPair


class TestKeyVersionPair():
    def test_from_uri(self):
        pair = KeyVersionPair.from_uri('/works/OL1W?v=7')
        assert pair.key == '/works/OL1W'
        assert pair.version == '7'
        pair = KeyVersionPair.from_uri('/authors/OL1A')
        assert pair.key == '/authors/OL1A'
        assert pair.version is None

    def test_to_uri(self):
        make = KeyVersionPair._make

        assert make(['/authors/OL1A', None]).to_uri() == '/authors/OL1A'
        assert make(['/works/OL1W', '7']).to_uri() == '/works/OL1W?v=7'


class FakeServer:
    """Mimics OpenLibrary's API class"""

    def __init__(self, docs):
        """
        :param list[dict] docs:
        """
        self.db = {}  # Mapping of key to (Mp of revision to doc)
        self.save_many(docs)

    def get(self, key, revision=None):
        """
        :param str key:
        :param int or None revision:
        :rtype: dict or None
        """
        revisions = self.db.get(key, {})
        if revision is None and len(revisions) > 0:
            return max(list(revisions.values()), key=lambda d: d['revision'])
        else:
            return revisions.get(revision, None)

    def get_many(self, keys):
        """
        :param list of str keys:
        :rtype: dict
        :return: Map of key to document
        """
        result = {}
        for k in keys:
            if k in self.db:
                result[k] = self.get(k)
        return result

    def save_many(self, docs, comment=None):
        """
        :param typing.List[dict] docs:
        :param str or None comment:
        """
        for doc in docs:
            key = doc['key']
            revision = doc['revision']
            if key not in self.db:
                self.db[key] = dict()
            self.db[doc['key']][revision] = doc


class TestCopy:
    def setup_method(self, method):
        self.docs = [
            {'key': '/works/OL1W', 'revision': 1, 'type': {'key': '/type/work'}},
            {'key': '/works/OL1W', 'revision': 2, 'type': {'key': '/type/work'}},
            {'key': '/works/OL1W', 'revision': 3, 'type': {'key': '/type/work'}},
            {'key': '/books/OL2M', 'revision': 1, 'type': {'key': '/type/edition'}},
        ]
        self.src = FakeServer(self.docs)
        self.dest = FakeServer([])

    def test_basic_copy(self):
        copy(self.src, self.dest, ['/books/OL2M'], 'asdf')
        assert self.dest.get('/books/OL2M') == self.src.get('/books/OL2M')
        assert len(self.dest.db) == 1

    def test_default_get_gets_latest_version(self):
        copy(self.src, self.dest, ['/works/OL1W'], 'asdf')
        assert self.dest.get('/works/OL1W') == self.src.get('/works/OL1W', 3)
        assert len(self.dest.db) == 1
        # Note revision would be 1 in the dest in actuality

    def test_getting_specific_version(self):
        copy(self.src, self.dest, ['/works/OL1W?v=1'], 'asdf')
        assert self.dest.get('/works/OL1W') == self.src.get('/works/OL1W', 1)
        assert len(self.dest.db) == 1
