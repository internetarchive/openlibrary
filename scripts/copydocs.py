#!/usr/bin/env python
from collections import namedtuple

import json
import os
import sys
from typing import Union

import web

from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

sys.path.insert(0, ".")  # Enable scripts/copydocs.py to be run.
import scripts._init_path  # noqa: E402,F401
from openlibrary.api import OpenLibrary, marshal  # noqa: E402

__version__ = "0.2"


def find(server, prefix):
    q = {'key~': prefix, 'limit': 1000}

    # until all properties and backreferences are deleted on production server
    if prefix == '/type':
        q['type'] = '/type/type'

    return [str(x) for x in server.query(q)]


def expand(server, keys):
    """
    Expands keys like "/templates/*" to be all template keys.

    :param Disk or OpenLibrary server:
    :param typing.Iterable[str] keys:
    :rtype: typing.Iterator[str]
    """
    if isinstance(server, Disk):
        yield from keys
    else:
        for key in keys:
            if key.endswith('*'):
                yield from find(server, key)
            else:
                yield key


class Disk:
    """Lets us copy templates from and records to the disk as files"""

    def __init__(self, root):
        self.root = root

    def get_many(self, keys):
        """
        Only gets templates
        :param typing.List[str] keys:
        :rtype: dict
        """

        def f(k):
            return {
                "key": k,
                "type": {"key": "/type/template"},
                "body": {
                    "type": "/type/text",
                    "value": open(self.root + k.replace(".tmpl", ".html")).read(),
                },
            }

        return {k: f(k) for k in keys}

    def save_many(self, docs, comment=None):
        """

        :param typing.List[dict or web.storage] docs:
        :param str or None comment: only here to match the signature of OpenLibrary api
        """

        def write(path, text):
            dir = os.path.dirname(path)
            if not os.path.exists(dir):
                os.makedirs(dir)

            if isinstance(text, dict):
                text = text['value']

            try:
                print("writing", path)
                f = open(path, "w")
                f.write(text)
                f.close()
            except OSError:
                print("failed", path)

        for doc in marshal(docs):
            path = os.path.join(self.root, doc['key'][1:])
            if doc['type']['key'] == '/type/template':
                path = path.replace(".tmpl", ".html")
                write(path, doc['body'])
            elif doc['type']['key'] == '/type/macro':
                path = path + ".html"
                write(path, doc['macro'])
            else:
                path = path + ".json"
                write(path, json.dumps(doc, indent=2))


def read_lines(filename):
    try:
        return [line.strip() for line in open(filename)]
    except OSError:
        return []


def get_references(doc, result=None):
    if result is None:
        result = []

    if isinstance(doc, list):
        for v in doc:
            get_references(v, result)
    elif isinstance(doc, dict):
        if 'key' in doc and len(doc) == 1:
            result.append(doc['key'])

        for k, v in doc.items():
            get_references(v, result)
    return result


class KeyVersionPair(namedtuple('KeyVersionPair', 'key version')):
    """Helper class to store uri's like /works/OL1W?v=2"""

    @staticmethod
    def from_uri(uri):
        """
        :param str uri: either something like /works/OL1W, /books/OL1M?v=3, etc.
        :rtype: KeyVersionPair
        """

        if '?v=' in uri:
            key, version = uri.split('?v=')
        else:
            key, version = uri, None
        return KeyVersionPair._make([key, version])

    def to_uri(self):
        """
        :rtype: str
        """
        uri = self.key
        if self.version:
            uri += '?v=' + self.version
        return uri

    def __str__(self):
        return self.to_uri()


def copy(
        src: Union[Disk, OpenLibrary],
        dest: Union[Disk, OpenLibrary],
        keys: list[str],
        comment: str,
        recursive=False,
        editions=False,
        saved: set[str] = None,
        cache: dict =None,
):
    """
    :param src: where we'll be copying form
    :param dest: where we'll be saving to
    :param comment: comment to writing when saving the documents
    :param recursive: Whether to recursively fetch an referenced docs
    :param editions: Whether to fetch editions of works as well
    :param saved: keys saved so far
    """
    if saved is None:
        saved = set()
    if cache is None:
        cache = {}

    def get_many(keys):
        docs = marshal(src.get_many(keys).values())
        # work records may contain excerpts, which reference the author of the excerpt.
        # Deleting them to prevent loading the users.
        for doc in docs:
            doc.pop('excerpts', None)

            # Authors are now with works. We don't need authors at editions.
            if doc['type']['key'] == '/type/edition':
                doc.pop('authors', None)

        return docs

    def fetch(uris):
        """
        :param typing.List[str] uris:
        :rtype: typing.List[dict or web.storage]
        """
        docs = []

        key_pairs = list(map(KeyVersionPair.from_uri, uris))

        for pair in key_pairs:
            if pair.key in cache:
                docs.append(cache[pair.key])

        key_pairs = [pair for pair in key_pairs if pair.to_uri() not in cache]

        unversioned_keys = [pair.key for pair in key_pairs if pair.version is None]
        versioned_to_get = [pair for pair in key_pairs if pair.version is not None]
        if unversioned_keys:
            print("fetching", unversioned_keys)
            docs2 = get_many(unversioned_keys)
            cache.update((doc['key'], doc) for doc in docs2)
            docs.extend(docs2)
        # Do versioned second so they can overwrite if necessary
        if versioned_to_get:
            print("fetching versioned", versioned_to_get)
            docs2 = [src.get(pair.key, int(pair.version)) for pair in versioned_to_get]
            cache.update((doc['key'], doc) for doc in docs2)
            docs.extend(docs2)

        return docs

    keys = [
        k
        for k in keys
        # Ignore /scan_record and /scanning_center ; they can cause infinite loops?
        if k not in saved and not k.startswith('/scan')]
    docs = fetch(keys)

    if editions:
        work_keys = [
            key
            for key in keys
            if key.startswith('/works/')
        ]

        assert isinstance(src, OpenLibrary), "fetching editions only works with OL src"
        if work_keys:
            # eg https://openlibrary.org/search.json?q=key:/works/OL102584W
            resp = src.search(
                'key:' + ' OR '.join(work_keys),
                limit=len(work_keys),
                fields=['edition_key'],
            )
            edition_keys = [
                f"/books/{olid}"
                for doc in resp['docs']
                for olid in doc['edition_key']
            ]
            if edition_keys:
                print("copying edition keys")
                copy(src, dest, edition_keys, comment, recursive=recursive, saved=saved,
                     cache=cache)

    if recursive:
        refs = get_references(docs)
        refs = [r for r in set(refs) if not r.startswith(("/type/", "/languages/"))]
        if refs:
            print("found references", refs)
            copy(src, dest, refs, comment, recursive=True, saved=saved, cache=cache)

    docs = [doc for doc in docs if doc['key'] not in saved]

    keys = [doc['key'] for doc in docs]
    print("saving", keys)
    # Sometimes saves in-explicably error ; check infobase logs
    # group things up to avoid a bad apple failing the batch
    for group in web.group(docs, 50):
        try:
            print(dest.save_many(group, comment=comment))
        except BaseException:
            print("Something went wrong saving this batch!")
    saved.update(keys)


def copy_list(src, dest, list_key, comment):
    keys = set()

    def jsonget(url):
        url = url.encode("utf-8")
        text = src._request(url).read()
        return json.loads(text)

    def get(key):
        print("get", key)
        return marshal(src.get(list_key))

    def query(**q):
        print("query", q)
        return [x['key'] for x in marshal(src.query(q))]

    def get_list_seeds(list_key):
        d = jsonget(list_key + "/seeds.json")
        return d['entries']  # [x['url'] for x in d['entries']]

    def add_seed(seed):
        if seed['type'] == 'edition':
            keys.add(seed['url'])
        elif seed['type'] == 'work':
            keys.add(seed['url'])
        elif seed['type'] == 'subject':
            doc = jsonget(seed['url'] + '.json')
            keys.update(w['key'] for w in doc['works'])

    seeds = get_list_seeds(list_key)
    for seed in seeds:
        add_seed(seed)

    edition_keys = {k for k in keys if k.startswith("/books/")}
    work_keys = {k for k in keys if k.startswith("/works/")}

    for w in work_keys:
        edition_keys.update(query(type='/type/edition', works=w, limit=500))

    keys = list(edition_keys) + list(work_keys)
    copy(src, dest, keys, comment=comment, recursive=True)


def main(
        keys: list[str],
        src="http://openlibrary.org/",
        dest="http://localhost:8080",
        comment="",
        recursive=True,
        editions=True,
        lists: list[str] = None,
        search: str = None,
        search_limit: int = 10,
):
    """
    Script to copy docs from one OL instance to another.
    Typically used to copy templates, macros, css and js from
    openlibrary.org to dev instance. paths can end with wildcards.

    USAGE:
        # Copy all templates
        ./scripts/copydocs.py --src http://openlibrary.org /templates/*
        # Copy specific records
        ./scripts/copydocs.py /authors/OL113592A /works/OL1098727W?v=2
        # Copy search results
        ./scripts/copydocs.py --search "publisher:librivox" --search-limit 10


    :param src: URL of the source open library server
    :param dest: URL of the destination open library server
    :param recursive: Recursively fetch all the referred docs
    :param editions: Also fetch all the editions of works
    :param lists: Copy docs from list(s)
    :param search: Run a search on open library and copy docs from the results
    """

    # Mypy doesn't handle union-ing types across if statements -_-
    # https://github.com/python/mypy/issues/6233
    src_ol: Union[Disk, OpenLibrary] = (
        OpenLibrary(src) if src.startswith("http://") else Disk(src))
    dest_ol: Union[Disk, OpenLibrary] = (
        OpenLibrary(dest) if dest.startswith("http://") else Disk(dest))

    if isinstance(dest_ol, OpenLibrary):
        section = "[%s]" % web.lstrips(dest, "http://").strip("/")
        if section in read_lines(os.path.expanduser("~/.olrc")):
            dest_ol.autologin()
        else:
            dest_ol.login("admin", "admin123")

    for list_key in (lists or []):
        copy_list(src_ol, dest_ol, list_key, comment=comment)

    if search:
        assert isinstance(src_ol, OpenLibrary), "Search only works with OL src"
        keys += [
            doc['key']
            for doc in src_ol.search(search, limit=search_limit, fields=['key'])['docs']
        ]

    keys = list(expand(src_ol, ('/' + k.lstrip('/') for k in keys)))

    copy(src_ol, dest_ol, keys, comment=comment, recursive=recursive, editions=editions)


if __name__ == '__main__':
    FnToCLI(main).run()
