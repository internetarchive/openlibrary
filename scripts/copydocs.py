#! /usr/bin/env python
"""Script to copy docs from one OL instance to another.
Typically used to copy templates, macros, css and js from
openlibrary.org to dev instance, defaulting to localhost.

USAGE:
    ./scripts/copydocs.py --src http://openlibrary.org /templates/*

This script can also be used to copy books and authors from OL to dev instance.

    ./scripts/copydocs.py /authors/OL113592A
    ./scripts/copydocs.py /works/OL1098727W?v=2
"""
from __future__ import absolute_import, print_function

from collections import namedtuple

import json
import os
import sys

import web

from optparse import OptionParser

import six

sys.path.insert(0, ".")  # Enable scripts/copydocs.py to be run.
import scripts._init_path  # noqa: E402,F401
from openlibrary.api import OpenLibrary, marshal  # noqa: E402

__version__ = "0.2"

def find(server, prefix):
    q = {'key~': prefix, 'limit': 1000}

    # until all properties and backreferences are deleted on production server
    if prefix == '/type':
        q['type'] = '/type/type'

    return [six.text_type(x) for x in server.query(q)]


def expand(server, keys):
    """
    Expands keys like "/templates/*" to be all template keys.

    :param Disk or OpenLibrary server:
    :param typing.List[str] keys:
    :rtype: typing.Iterator[str]
    """
    if isinstance(server, Disk):
        for k in keys:
            yield k
    else:
        for key in keys:
            if key.endswith('*'):
                for k in find(server, key):
                    yield k
            else:
                yield key


desc = """Script to copy docs from one OL instance to another.
Typically used to copy templates, macros, css and js from
openlibrary.org to dev instance. paths can end with wildcards.
"""
def parse_args():
    parser = OptionParser("usage: %s [options] path1 path2" % sys.argv[0], description=desc, version=__version__)
    parser.add_option("-c", "--comment", dest="comment", default="", help="comment")
    parser.add_option("--src", dest="src", metavar="SOURCE_URL", default="http://openlibrary.org/", help="URL of the source server (default: %default)")
    parser.add_option("--dest", dest="dest", metavar="DEST_URL",
                      default="http://localhost:8080",
                      help="URL of the destination server (default: %default)")
    parser.add_option("-r", "--recursive", dest="recursive", action='store_true', default=True, help="Recursively fetch all the referred docs.")
    parser.add_option("-l", "--list", dest="lists", action="append", default=[], help="copy docs from a list.")
    return parser.parse_args()


class Disk:
    """Lets us copy templates from and records to the disk as files """

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
                    "value": open(self.root + k.replace(".tmpl", ".html")).read()
                }
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
            except IOError:
                print("failed", path)

        for doc in marshal(docs):
            path = os.path.join(self.root, doc['key'][1:])
            if doc['type']['key'] == '/type/template':
                path = path.replace(".tmpl", ".html")
                write(path, doc['body'])
            elif doc['type']['key'] == '/type/macro':
                path = path + ".html"
                write(path, doc['macro'])

def read_lines(filename):
    try:
        return [line.strip() for line in open(filename)]
    except IOError:
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


def copy(src, dest, keys, comment, recursive=False, saved=None, cache=None):
    """
    :param Disk or OpenLibrary src: where we'll be copying form
    :param Disk or OpenLibrary dest: where we'll be saving to
    :param typing.List[str] keys:
    :param str comment: commit to writing when saving the documents
    :param bool recursive:
    :param typing.Set[str] or None saved: keys saved so far
    :param dict or None cache:
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

    keys = [k for k in keys if k not in saved]
    docs = fetch(keys)

    if recursive:
        refs = get_references(docs)
        refs = [r for r in list(set(refs)) if not r.startswith("/type/") and not r.startswith("/languages/")]
        if refs:
            print("found references", refs)
            copy(src, dest, refs, comment, recursive=True, saved=saved, cache=cache)

    docs = [doc for doc in docs if doc['key'] not in saved]

    keys = [doc['key'] for doc in docs]
    print("saving", keys)
    print(dest.save_many(docs, comment=comment))
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
        return d['entries'] #[x['url'] for x in d['entries']]

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

    edition_keys = set(k for k in keys if k.startswith("/books/"))
    work_keys = set(k for k in keys if k.startswith("/works/"))

    for w in work_keys:
        edition_keys.update(query(type='/type/edition', works=w, limit=500))

    keys = list(edition_keys) + list(work_keys)
    copy(src, dest, keys, comment=comment, recursive=True)

def main():
    options, args = parse_args()

    if options.src.startswith("http://"):
        src = OpenLibrary(options.src)
    else:
        src = Disk(options.src)

    if options.dest.startswith("http://"):
        dest = OpenLibrary(options.dest)
        section = "[%s]" % web.lstrips(options.dest, "http://").strip("/")
        if section in read_lines(os.path.expanduser("~/.olrc")):
            dest.autologin()
        else:
            dest.login("admin", "admin123")
    else:
        dest = Disk(options.dest)

    for list_key in options.lists:
        copy_list(src, dest, list_key, comment=options.comment)

    keys = args
    keys = list(expand(src, keys))

    copy(src, dest, keys, comment=options.comment, recursive=options.recursive)

if __name__ == '__main__':
    main()
