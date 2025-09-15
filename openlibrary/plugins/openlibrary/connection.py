"""Open Library extension to provide a new kind of client connection with caching support."""

import datetime
import json
import logging

import web

from infogami import config
from infogami.infobase import client
from infogami.utils import stats
from openlibrary.core import ia

logger = logging.getLogger("openlibrary")


class ConnectionMiddleware:
    response_type = "json"

    def __init__(self, conn):
        self.conn = conn

    def get_auth_token(self):
        return self.conn.get_auth_token()

    def set_auth_token(self, token):
        self.conn.set_auth_token(token)

    def request(self, sitename, path, method='GET', data=None):
        if path == '/get':
            return self.get(sitename, data)
        elif path == '/get_many':
            return self.get_many(sitename, data)
        elif path == '/versions':
            return self.versions(sitename, data)
        elif path == '/_recentchanges':
            return self.recentchanges(sitename, data)
        elif path == '/things':
            return self.things(sitename, data)
        elif path == '/write':
            return self.write(sitename, data)
        elif path.startswith('/save/'):
            return self.save(sitename, path, data)
        elif path == '/save_many':
            return self.save_many(sitename, data)
        elif path.startswith("/_store/") and not path.startswith("/_store/_"):
            if method == 'GET':
                return self.store_get(sitename, path)
            elif method == 'PUT':
                return self.store_put(sitename, path, data)
            elif method == 'DELETE':
                return self.store_delete(sitename, path, data)
        elif path == "/_store/_save_many" and method == 'POST':
            # save multiple things at once
            return self.store_put_many(sitename, data)
        elif path.startswith("/account"):
            return self.account_request(sitename, path, method, data)

        return self.conn.request(sitename, path, method, data)

    def account_request(self, sitename, path, method="GET", data=None):
        return self.conn.request(sitename, path, method, data)

    def get(self, sitename, data):
        return self.conn.request(sitename, '/get', 'GET', data)

    def get_many(self, sitename, data):
        return self.conn.request(sitename, '/get_many', 'GET', data)

    def versions(self, sitename, data):
        return self.conn.request(sitename, '/versions', 'GET', data)

    def recentchanges(self, sitename, data):
        return self.conn.request(sitename, '/_recentchanges', 'GET', data)

    def things(self, sitename, data):
        return self.conn.request(sitename, '/things', 'GET', data)

    def write(self, sitename, data):
        return self.conn.request(sitename, '/write', 'POST', data)

    def save(self, sitename, path, data):
        return self.conn.request(sitename, path, 'POST', data)

    def save_many(self, sitename, data):
        # Work-around for https://github.com/internetarchive/openlibrary/issues/4285
        # Infogami seems to read encoded bytes as a string with a byte literal inside
        # of it, which is invalid JSON and also can't be decode()'d.
        if isinstance(data.get('query'), bytes):
            data['query'] = data['query'].decode()
        return self.conn.request(sitename, '/save_many', 'POST', data)

    def store_get(self, sitename, path):
        return self.conn.request(sitename, path, 'GET')

    def store_put(self, sitename, path, data):
        return self.conn.request(sitename, path, 'PUT', data)

    def store_put_many(self, sitename, data):
        return self.conn.request(sitename, "/_store/_save_many", 'POST', data)

    def store_delete(self, sitename, path, data):
        return self.conn.request(sitename, path, 'DELETE', data)


_memcache = None


class IAMiddleware(ConnectionMiddleware):
    def _get_itemid(self, key):
        """Returns internet archive item id from the key.

        If the key is of the form "/books/ia:.*", the part after "/books/ia:"
        is returned, otherwise None is returned.
        """
        if key and key.startswith("/books/ia:") and key.count("/") == 2:
            return key[len("/books/ia:") :]

    def get(self, sitename, data):
        key = data.get('key')

        if itemid := self._get_itemid(key):
            edition_key = self._find_edition(sitename, itemid)
            if edition_key:
                # Delete the store entry, indicating that this is no more is an item to be imported.
                self._ensure_no_store_entry(sitename, itemid)
                return self._make_redirect(itemid, edition_key)
            else:
                metadata = ia.get_metadata(itemid)
                doc = ia.edition_from_item_metadata(itemid, metadata)

                if doc is None:
                    # Delete store entry, if it exists.
                    # When an item is darked on archive.org, it should be
                    # automatically removed from OL. Removing entry from store
                    # will trigger the solr-updater to delete it from solr as well.
                    self._ensure_no_store_entry(sitename, itemid)

                    raise client.ClientException(
                        "404 Not Found",
                        "notfound",
                        json.dumps({"key": "/books/ia:" + itemid, "error": "notfound"}),
                    )

                storedoc = self._ensure_store_entry(sitename, itemid)

                # Hack to add additional subjects /books/ia: pages
                # Adding subjects to store docs, will add these subjects to the books.
                # These subjects are used when indexing the books in solr.
                if storedoc.get("subjects"):
                    doc.setdefault("subjects", []).extend(storedoc['subjects'])
                return json.dumps(doc)
        else:
            return ConnectionMiddleware.get(self, sitename, data)

    def _find_edition(self, sitename, itemid):
        # match ocaid
        q = {"type": "/type/edition", "ocaid": itemid}
        keys_json = ConnectionMiddleware.things(
            self, sitename, {"query": json.dumps(q)}
        )
        keys = json.loads(keys_json)
        if keys:
            return keys[0]

        # Match source_records
        # When there are multiple scan for the same edition, only scan_records is updated.
        q = {"type": "/type/edition", "source_records": "ia:" + itemid}
        keys_json = ConnectionMiddleware.things(
            self, sitename, {"query": json.dumps(q)}
        )
        keys = json.loads(keys_json)
        if keys:
            return keys[0]

    def _make_redirect(self, itemid, location):
        timestamp = {"type": "/type/datetime", "value": "2010-01-01T00:00:00"}
        d = {
            "key": "/books/ia:" + itemid,
            "type": {"key": "/type/redirect"},
            "location": location,
            "revision": 1,
            "created": timestamp,
            "last_modified": timestamp,
        }
        return json.dumps(d)

    def _ensure_no_store_entry(self, sitename, identifier):
        key = "ia-scan/" + identifier
        store_key = "/_store/" + key
        # If the entry is found, delete it
        try:
            self.store_get(sitename, store_key)
            self.store_delete(sitename, store_key, {"_rev": None})
        except client.ClientException:
            # nothing to do if that doesn't exist
            pass

    def _ensure_store_entry(self, sitename, identifier):
        key = "ia-scan/" + identifier
        store_key = "/_store/" + key
        # If the entry is not found, create an entry
        try:
            jsontext = self.store_get(sitename, store_key)
            return json.loads(jsontext)
        except client.ClientException as e:
            logger.error("error", exc_info=True)
            if e.status.startswith("404"):
                doc = {
                    "_key": key,
                    "type": "ia-scan",
                    "identifier": identifier,
                    "created": datetime.datetime.utcnow().isoformat(),
                }
                self.store_put(sitename, store_key, json.dumps(doc))
                return doc
        except:
            logger.error("error", exc_info=True)

    def versions(self, sitename, data):
        # handle the query of type {"query": '{"key": "/books/ia:foo00bar", ...}}
        if 'query' in data:
            q = json.loads(data['query'])
            itemid = self._get_itemid(q.get('key'))
            if itemid:
                key = q['key']
                return json.dumps([self.dummy_edit(key)])

        # if not just go the default way
        return ConnectionMiddleware.versions(self, sitename, data)

    def recentchanges(self, sitename, data):
        # handle the query of type {"query": '{"key": "/books/ia:foo00bar", ...}}
        if 'query' in data:
            q = json.loads(data['query'])
            itemid = self._get_itemid(q.get('key'))
            if itemid:
                key = q['key']
                return json.dumps([self.dummy_recentchange(key)])

        # if not just go the default way
        return ConnectionMiddleware.recentchanges(self, sitename, data)

    def dummy_edit(self, key):
        return {
            "comment": "",
            "author": None,
            "ip": "127.0.0.1",
            "created": "2012-01-01T00:00:00",
            "bot": False,
            "key": key,
            "action": "edit-book",
            "changes": json.dumps({"key": key, "revision": 1}),
            "revision": 1,
            "kind": "update",
            "id": "0",
            "timestamp": "2010-01-01T00:00:00",
            "data": {},
        }

    def dummy_recentchange(self, key):
        return {
            "comment": "",
            "author": None,
            "ip": "127.0.0.1",
            "timestamp": "2012-01-01T00:00:00",
            "data": {},
            "changes": [{"key": key, "revision": 1}],
            "kind": "update",
            "id": "0",
        }


class MemcacheMiddleware(ConnectionMiddleware):
    def __init__(self, conn, memcache_servers):
        ConnectionMiddleware.__init__(self, conn)
        self.memcache = self.get_memcache(memcache_servers)

    def get_memcache(self, memcache_servers):
        global _memcache
        if _memcache is None:
            from openlibrary.utils import olmemcache  # noqa: PLC0415

            _memcache = olmemcache.Client(memcache_servers)
        return _memcache

    def get(self, sitename, data):
        key = data.get('key')
        revision = data.get('revision')

        if key.startswith("_"):
            # Don't cache keys that starts with _ to avoid considering _store/foo as things.
            # The _store stuff is used for storing infobase store docs.
            return ConnectionMiddleware.get(self, sitename, data)

        if revision is None:
            stats.begin("memcache.get", key=key)
            result = self.memcache.get(key)
            stats.end(hit=bool(result))

            return result or ConnectionMiddleware.get(self, sitename, data)
        else:
            # cache get requests with revisions for a minute
            mc_key = "%s@%d" % (key, revision)
            result = self.mc_get(mc_key)
            if result is None:
                result = ConnectionMiddleware.get(self, sitename, data)
                if result:
                    self.mc_set(mc_key, result, time=60)  # cache for a minute
            return result

    def get_many(self, sitename, data):
        keys = json.loads(data['keys'])

        stats.begin("memcache.get_multi")
        result = self.memcache.get_multi(keys)
        stats.end(found=len(result))

        keys2 = [k for k in keys if k not in result]
        if keys2:
            data['keys'] = json.dumps(keys2)
            result2 = ConnectionMiddleware.get_many(self, sitename, data)
            result2 = json.loads(result2)

            # Memcache expects dict with (key, json) mapping and we have (key, doc) mapping.
            # Converting the docs to json before passing to memcache.
            self.mc_set_multi({key: json.dumps(doc) for key, doc in result2.items()})

            result.update(result2)

        # @@ too many JSON conversions
        for k in result:
            if isinstance(result[k], str):
                result[k] = json.loads(result[k])

        return json.dumps(result)

    def mc_get(self, key):
        stats.begin("memcache.get", key=key)
        result = self.memcache.get(key)
        stats.end(hit=bool(result))
        return result

    def mc_delete(self, key):
        stats.begin("memcache.delete", key=key)
        self.memcache.delete(key)
        stats.end()

    def mc_add(self, key, value, time=0):
        stats.begin("memcache.add", key=key, time=time)
        self.memcache.add(key, value)
        stats.end()

    def mc_set(self, key, value, time=0):
        stats.begin("memcache.set", key=key)
        self.memcache.add(key, value, time=time)
        stats.end()

    def mc_set_multi(self, mapping):
        stats.begin("memcache.set_multi")
        self.memcache.set_multi(mapping)
        stats.end()

    def mc_delete_multi(self, keys):
        stats.begin("memcache.delete_multi")
        self.memcache.delete_multi(keys)
        stats.end()

    def store_get(self, sitename, path):
        # path will be "/_store/$key"
        result = self.mc_get(path)

        if result is None:
            result = ConnectionMiddleware.store_get(self, sitename, path)
            if result:
                self.mc_set(path, result, 3600)  # cache it only for one hour
        return result

    def store_put(self, sitename, path, data):
        # path will be "/_store/$key"

        # deleting before put to make sure the entry is deleted even if the
        # process dies immediately after put.
        # Still there is very very small chance of invalid cache if someone else
        # updates memcache after stmt-1 and this process dies after stmt-2.
        self.mc_delete(path)
        result = ConnectionMiddleware.store_put(self, sitename, path, data)
        self.mc_delete(path)
        return result

    def store_put_many(self, sitename, datajson):
        data = json.loads(datajson)
        mc_keys = ["/_store/" + doc['_key'] for doc in data]
        self.mc_delete_multi(mc_keys)
        result = ConnectionMiddleware.store_put_many(self, sitename, datajson)
        self.mc_delete_multi(mc_keys)
        return result

    def store_delete(self, sitename, key, data):
        # see comment in store_put
        self.mc_delete(key)
        result = ConnectionMiddleware.store_delete(self, sitename, key, data)
        self.mc_delete(key)
        return result

    def account_request(self, sitename, path, method="GET", data=None):
        # For post requests, remove the account entry from the cache.
        if method == "POST" and isinstance(data, dict):
            deletes = []
            if 'username' in data:
                deletes.append("/_store/account/" + data["username"])

                # get the email from account doc and invalidate the email.
                # required in cases of email change.
                try:
                    docjson = self.store_get(
                        sitename, "/_store/account/" + data['username']
                    )
                    doc = json.loads(docjson)
                    deletes.append("/_store/account-email/" + doc["email"])
                    deletes.append("/_store/account-email/" + doc["email"].lower())
                except client.ClientException:
                    # ignore
                    pass
            if 'email' in data:
                # if email is being passed, that that email doc is likely to be changed.
                # remove that also from cache.
                deletes.append("/_store/account-email/" + data["email"])
                deletes.append("/_store/account-email/" + data["email"].lower())

            self.mc_delete_multi(deletes)
            result = ConnectionMiddleware.account_request(
                self, sitename, path, method, data
            )
            self.mc_delete_multi(deletes)
        else:
            result = ConnectionMiddleware.account_request(
                self, sitename, path, method, data
            )
        return result


class MigrationMiddleware(ConnectionMiddleware):
    """Temporary middleware to handle upstream to www migration."""

    def _process_key(self, key):
        mapping = (
            "/l/",
            "/languages/",
            "/a/",
            "/authors/",
            "/b/",
            "/books/",
            "/user/",
            "/people/",
        )

        if "/" in key and key.split("/")[1] in ['a', 'b', 'l', 'user']:
            for old, new in web.group(mapping, 2):
                if key.startswith(old):
                    return new + key[len(old) :]
        return key

    def exists(self, key):
        try:
            ConnectionMiddleware.get(self, "openlibrary.org", {"key": key})
            return True
        except client.ClientException:
            return False

    def _process(self, data):
        if isinstance(data, list):
            return [self._process(d) for d in data]
        elif isinstance(data, dict):
            if 'key' in data:
                data['key'] = self._process_key(data['key'])
            return {k: self._process(v) for k, v in data.items()}
        else:
            return data

    def get(self, sitename, data):
        if web.ctx.get('path') == "/api/get" and 'key' in data:
            data['key'] = self._process_key(data['key'])

        response = ConnectionMiddleware.get(self, sitename, data)
        if response:
            data = json.loads(response)
            data = self._process(data)
            data = data and self.fix_doc(data)
            response = json.dumps(data)
        return response

    def fix_doc(self, doc):
        type = doc.get("type", {}).get("key")

        if type == "/type/work":
            if doc.get("authors"):
                # some record got empty author records because of an error
                # temporary hack to fix
                doc['authors'] = [
                    a for a in doc['authors'] if 'author' in a and 'key' in a['author']
                ]
        elif type == "/type/edition" and 'title_prefix' in doc:
            # get rid of title_prefix.
            title = doc['title_prefix'].strip() + ' ' + doc.get('title', '')
            doc['title'] = title.strip()
            del doc['title_prefix']

        return doc

    def fix_broken_redirect(self, key):
        """Some work/edition records references to redirected author records
        and that is making save fail.

        This is a hack to work-around that issue.
        """
        json_data = self.get("openlibrary.org", {"key": key})
        if json:
            doc = json.loads(json_data)
            if (
                doc.get("type", {}).get("key") == "/type/redirect"
                and doc.get('location') is not None
            ):
                return doc['location']
        return key

    def get_many(self, sitename, data):
        response = ConnectionMiddleware.get_many(self, sitename, data)
        if response:
            data = json.loads(response)
            data = self._process(data)
            data = {key: self.fix_doc(doc) for key, doc in data.items()}
            response = json.dumps(data)
        return response


class HybridConnection(client.Connection):
    """Infobase connection made of both local and remote connections.

    The local connection is used for reads and the remote connection is used for writes.

    Some services in the OL infrastructure depends of the log written by the
    writer, so remote connection is used, which takes care of writing logs. By
    using a local connection for reads improves the performance by cutting
    down the overhead of http calls present in case of remote connections.
    """

    def __init__(self, reader, writer):
        client.Connection.__init__(self)
        self.reader = reader
        self.writer = writer

    def set_auth_token(self, token):
        self.reader.set_auth_token(token)
        self.writer.set_auth_token(token)

    def get_auth_token(self):
        return self.writer.get_auth_token()

    def request(self, sitename, path, method="GET", data=None):
        if method == "GET":
            return self.reader.request(sitename, path, method, data=data)
        else:
            return self.writer.request(sitename, path, method, data=data)


@web.memoize
def _update_infobase_config():
    """Updates infobase config when this function is called for the first time.

    From next time onwards, it doesn't do anything because this function is memoized.
    """
    # update infobase configuration
    from infogami.infobase import server  # noqa: PLC0415

    if not config.get("infobase"):
        config.infobase = {}
    # This sets web.config.db_parameters
    server.update_config(config.infobase)


def create_local_connection():
    _update_infobase_config()
    return client.connect(type='local', **web.config.db_parameters)


def create_remote_connection():
    return client.connect(type='remote', base_url=config.infobase_server)


def create_hybrid_connection():
    local = create_local_connection()
    remote = create_remote_connection()
    return HybridConnection(local, remote)


def OLConnection():
    """Create a connection to Open Library infobase server."""

    def create_connection():
        if config.get("connection_type") == "hybrid":
            return create_hybrid_connection()
        elif config.get('infobase_server'):
            return create_remote_connection()
        elif config.get("infobase", {}).get('db_parameters'):
            return create_local_connection()
        else:
            raise Exception("db_parameters are not specified in the configuration")

    conn = create_connection()
    if config.get('memcache_servers'):
        conn = MemcacheMiddleware(conn, config.get('memcache_servers'))

    if config.get('upstream_to_www_migration'):
        conn = MigrationMiddleware(conn)

    conn = IAMiddleware(conn)
    return conn
