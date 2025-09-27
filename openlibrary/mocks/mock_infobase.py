"""Simple implementation of mock infogami site to use in testing."""

import glob
import itertools
import json
import re
from datetime import datetime

import pytest
import web

from infogami import config
from infogami.infobase import account, client, common
from infogami.infobase import config as infobase_config
from openlibrary.plugins.upstream.models import Changeset
from openlibrary.plugins.upstream.utils import safeget

key_patterns = {
    'work': '/works/OL%dW',
    'edition': '/books/OL%dM',
    'author': '/authors/OL%dA',
}


class MockSite:
    def __init__(self):
        self.reset()

    def reset(self):
        self.store = MockStore()
        if config.get('infobase') is None:
            config.infobase = {}

        infobase_config.secret_key = "foobar"
        config.infobase['secret_key'] = "foobar"

        self.account_manager = self.create_account_manager()

        self._cache = {}
        self.docs = {}
        self.docs_historical = {}
        self.changesets = []
        self.index = []
        self.keys = {'work': 0, 'author': 0, 'edition': 0}

    def create_account_manager(self):
        # Hack to use the accounts stuff from Infogami
        infobase_config.user_root = "/people"

        store = web.storage(store=self.store)
        site = web.storage(store=store, save_many=self.save_many)
        return account.AccountManager(site, config.infobase['secret_key'])

    def _save_doc(self, query, timestamp):
        key = query['key']

        if key in self.docs:
            rev = self.docs[key]['revision'] + 1
        else:
            rev = 1

        doc = dict(query)
        doc['revision'] = rev
        doc['latest_revision'] = rev
        doc['last_modified'] = {
            "type": "/type/datetime",
            "value": timestamp.isoformat(),
        }
        if rev == 1:
            doc['created'] = doc['last_modified']
        else:
            doc['created'] = self.docs[key]['created']

        self.docs[key] = doc
        self.docs_historical[(key, rev)] = doc

        return doc

    def save(
        self, query, comment=None, action=None, data=None, timestamp=None, author=None
    ):
        timestamp = timestamp or datetime.now()

        if author:
            author = {"key": author.key}

        doc = self._save_doc(query, timestamp)

        changes = [web.storage({"key": doc['key'], "revision": doc['revision']})]
        changeset = self._make_changeset(
            timestamp=timestamp,
            kind=action,
            comment=comment,
            data=data,
            changes=changes,
            author=author,
        )
        self.changesets.append(changeset)

        self.reindex(doc)

    def save_many(
        self, query, comment=None, action=None, data=None, timestamp=None, author=None
    ):
        timestamp = timestamp or datetime.now()
        docs = [self._save_doc(doc, timestamp) for doc in query]

        if author:
            author = {"key": author.key}

        changes = [
            web.storage({"key": doc['key'], "revision": doc['revision']})
            for doc in docs
        ]
        changeset = self._make_changeset(
            timestamp=timestamp,
            kind=action,
            comment=comment,
            data=data,
            changes=changes,
            author=author,
        )

        self.changesets.append(changeset)
        for doc in docs:
            self.reindex(doc)

    def quicksave(self, key, type="/type/object", **kw):
        """Handy utility to save an object with less code and get the saved object as return value.

        foo = mock_site.quicksave("/books/OL1M", "/type/edition", title="Foo")
        """
        query = {
            "key": key,
            "type": {"key": type},
        }
        query.update(kw)
        self.save(query)
        return self.get(key)

    def _make_changeset(self, timestamp, kind, comment, data, changes, author=None):
        id = len(self.changesets)
        return {
            "id": id,
            "kind": kind or "update",
            "comment": comment,
            "data": data or {},
            "changes": changes,
            "timestamp": timestamp.isoformat(),
            "author": author,
            "ip": "127.0.0.1",
            "bot": False,
        }

    def get_change(self, cid: int) -> Changeset:
        return Changeset(self, self.changesets[cid])

    def recentchanges(self, query):
        limit = query.pop("limit", 1000)
        offset = query.pop("offset", 0)

        author = query.pop("author", None)

        if not author:
            raise NotImplementedError(
                "MockSite.recentchanges without author not implemented"
            )

        result = list(
            itertools.islice(
                (
                    Changeset(self, c)
                    for c in reversed(self.changesets)
                    if safeget(lambda: c['author']['key']) == author
                ),
                offset,
                offset + limit,
            )
        )

        return result

    def get(self, key, revision=None, lazy=False):
        if revision:
            data = self.docs_historical.get((key, revision))
        else:
            data = self.docs.get(key)

        data = data and web.storage(common.parse_query(data))
        return data and client.create_thing(self, key, self._process_dict(data))

    def _process(self, value):
        if isinstance(value, list):
            return [self._process(v) for v in value]
        elif isinstance(value, dict):
            d = {}
            for k, v in value.items():
                d[k] = self._process(v)
            return client.create_thing(self, d.get('key'), d)
        elif isinstance(value, common.Reference):
            return client.create_thing(self, str(value), None)
        else:
            return value

    def _process_dict(self, data):
        d = {}
        for k, v in data.items():
            d[k] = self._process(v)
        return d

    def get_many(self, keys):
        return [self.get(k) for k in keys if k in self.docs]

    def things(self, query):
        limit = query.pop('limit', 100)
        offset = query.pop('offset', 0)

        keys = set(self.docs)

        for k, v in query.items():
            if isinstance(v, dict):
                # query keys need to be flattened properly,
                # this corrects any nested keys that have been included
                # in values.
                flat = common.flatten_dict(v)[0]
                k = web.rstrips(k + '.' + flat[0], '.key')
                v = flat[1]
            keys = {k for k in self.filter_index(self.index, k, v) if k in keys}

        keys = sorted(keys)
        return keys[offset : offset + limit]

    def regex_ilike(self, pattern: str, text: str) -> bool:
        """Construct a regex pattern for ILIKE operation and match against the text."""
        # Remove '_' to ignore single character matches, the same as Infobase.
        regex_pattern = re.escape(pattern).replace(r"\*", ".*").replace("_", "")
        return bool(re.match(regex_pattern, text, re.IGNORECASE))

    def filter_index(self, index, name, value):
        operations = {
            "~": lambda i, value: isinstance(i.value, str)
            and self.regex_ilike(value, i.value),
            "<": lambda i, value: i.value < value,
            ">": lambda i, value: i.value > value,
            "!": lambda i, value: i.value != value,
            "=": lambda i, value: i.value == value,
        }
        pattern = ".*([%s])$" % "".join(operations)
        rx = web.re_compile(pattern)

        if m := rx.match(name):
            op = m.group(1)
            name = name[:-1]
        else:
            op = "="

        f = operations[op]

        if name == 'isbn_':
            names = ['isbn_10', 'isbn_13']
        else:
            names = [name]

        if isinstance(value, list):  # Match any of the elements in value if it's a list
            for n in names:
                for i in index:
                    if i.name == n and any(f(i, v) for v in value):
                        yield i.key
        else:  # Otherwise just match directly
            for n in names:
                for i in index:
                    if i.name == n and f(i, value):
                        yield i.key

    def compute_index(self, doc):
        key = doc['key']
        index = common.flatten_dict(doc)

        for k, v in index:
            # for handling last_modified.value
            if k.endswith(".value"):
                k = web.rstrips(k, ".value")

            if k.endswith(".key"):
                yield web.storage(
                    key=key, datatype="ref", name=web.rstrips(k, ".key"), value=v
                )
            elif isinstance(v, str):
                yield web.storage(key=key, datatype="str", name=k, value=v)
            elif isinstance(v, int):
                yield web.storage(key=key, datatype="int", name=k, value=v)

    def reindex(self, doc):
        self.index = [i for i in self.index if i.key != doc['key']]
        self.index.extend(self.compute_index(doc))

    def find_user_by_email(self, email):
        return None

    def versions(self, q):
        return []

    def _get_backreferences(self, doc):
        return {}

    def _load(self, key, revision=None):
        doc = self.get(key, revision=revision)
        data = doc.dict()
        data = web.storage(common.parse_query(data))
        return self._process_dict(data)

    def new(self, key, data=None):
        """Creates a new thing in memory."""
        data = common.parse_query(data)
        data = self._process_dict(data or {})
        return client.create_thing(self, key, data)

    def new_key(self, type):
        assert type.startswith('/type/')
        t = type[6:]
        self.keys[t] += 1
        return key_patterns[t] % self.keys[t]

    def register(self, username, displayname, email, password):
        try:
            self.account_manager.register(
                username=username,
                email=email,
                password=password,
                data={"displayname": displayname},
            )
        except common.InfobaseException as e:
            raise client.ClientException("bad_data", str(e))

    def activate_account(self, username):
        try:
            self.account_manager.activate(username=username)
        except common.InfobaseException as e:
            raise client.ClientException(str(e))

    def update_account(self, username, **kw):
        status = self.account_manager.update(username, **kw)
        if status != "ok":
            raise client.ClientException("bad_data", "Account activation failed.")

    def login(self, username, password):
        status = self.account_manager.login(username, password)
        if status == "ok":
            self.account_manager.set_auth_token("/people/" + username)
        else:
            d = {"code": status}
            raise client.ClientException(
                "bad_data", msg="Login failed", json=json.dumps(d)
            )

    def find_account(self, username=None, email=None):
        if username is not None:
            return self.store.get("account/" + username)
        else:
            try:
                return self.store.values(type="account", name="email", value=email)[0]
            except IndexError:
                return None

    def get_user(self):
        if auth_token := web.ctx.get("infobase_auth_token", ""):
            try:
                user_key, login_time, digest = auth_token.split(',')
            except ValueError:
                return

            a = self.account_manager
            if a._check_salted_hash(a.secret_key, user_key + "," + login_time, digest):
                return self.get(user_key)


class MockConnection:
    def get_auth_token(self):
        return web.ctx.infobase_auth_token

    def set_auth_token(self, token):
        web.ctx.infobase_auth_token = token


class MockStore(dict):
    def __setitem__(self, key, doc):
        doc['_key'] = key
        dict.__setitem__(self, key, doc)

    put = __setitem__

    def put_many(self, docs):
        self.update((doc['_key'], doc) for doc in docs)

    def _query(self, type=None, name=None, value=None, limit=100, offset=0):
        for doc in dict.values(self):
            if type is not None and doc.get("type", "") != type:
                continue
            if name is not None and doc.get(name) != value:
                continue

            yield doc

    def keys(self, **kw):
        return [doc['_key'] for doc in self._query(**kw)]

    def values(self, **kw):
        return list(self._query(**kw))

    def items(self, **kw):
        return [(doc["_key"], doc) for doc in self._query(**kw)]


@pytest.fixture
def mock_site(request):
    """mock_site funcarg.

    Creates a mock site, assigns it to web.ctx.site and returns it.
    """

    def read_types():
        for path in glob.glob("openlibrary/plugins/openlibrary/types/*.type"):
            with open(path) as file:
                text = file.read()
            doc = eval(text, {'true': True, 'false': False})
            if isinstance(doc, list):
                yield from doc
            else:
                yield doc

    def setup_models():
        from openlibrary.plugins.upstream import models  # noqa: PLC0415

        models.setup()

    site = MockSite()

    setup_models()
    for doc in read_types():
        site.save(doc)

    old_ctx = dict(web.ctx)
    web.ctx.clear()
    web.ctx.site = site
    web.ctx.conn = MockConnection()
    web.ctx.env = web.ctx.environ = web.storage()
    web.ctx.headers = []

    yield site

    web.ctx.clear()
    web.ctx.update(old_ctx)
