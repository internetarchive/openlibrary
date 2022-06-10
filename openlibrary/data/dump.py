"""Library for generating and processing Open Library data dumps.

Glossary:

* dump - Dump of latest revisions of all documents.
* cdump - Complete dump. Dump of all revisions of all documents.
* idump - Incremental dump. Dump of all revisions created in the given day.
"""

import gzip
import itertools
import json
import logging
import os
import re
import sys
from datetime import datetime

import web

from openlibrary.data import db
from openlibrary.data.sitemap import generate_html_index, generate_sitemaps
from openlibrary.plugins.openlibrary.processors import urlsafe

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


def log(*args) -> None:
    args_str = " ".join(str(a) for a in args)
    msg = f"{datetime.now():%Y-%m-%d %H:%M:%S} [openlibrary.dump] {args_str}"
    logger.info(msg)
    print(msg, file=sys.stderr)


def print_dump(json_records, filter=None):
    """Print the given json_records in the dump format."""
    start_time = datetime.now()
    for i, raw_json_data in enumerate(json_records):
        if i % 1_000_000 == 0:
            log(f"print_dump {i:,}")
        d = json.loads(raw_json_data)
        d.pop("id", None)
        d = _process_data(d)

        key = web.safestr(d["key"])

        # skip user and admin pages
        if key.startswith(("/people/", "/admin/")):
            continue

        # skip obsolete pages. Obsolete pages include volumes, scan_records and users
        # marked as spam.
        if key.startswith(("/b/", "/scan", "/old/")) or not key.startswith("/"):
            continue

        if filter and not filter(d):
            continue

        type_key = d["type"]["key"]
        timestamp = d["last_modified"]["value"]
        json_data = json.dumps(d)

        print("\t".join([type_key, key, str(d["revision"]), timestamp, json_data]))
    minutes = (datetime.now() - start_time).seconds // 60
    log(f"    print_dump() processed {i:,} records in {minutes:,} minutes.")


def read_data_file(filename: str, max_lines: int = 0):
    """
    max_lines allows us to test the process with a subset of all records.
    Setting max_lines to 0 will processes all records.
    """
    start_time = datetime.now()
    log(f"read_data_file({filename}, max_lines={max_lines if max_lines else 'all'})")
    for i, line in enumerate(xopen(filename, "rt")):
        thing_id, revision, json_data = line.strip().split("\t")
        yield pgdecode(json_data)
        if max_lines and i >= max_lines:
            break
    minutes = (datetime.now() - start_time).seconds // 60
    log(f"read_data_file() processed {i:,} records in {minutes:,} minutes.")


def xopen(path: str, mode: str):
    if path.endswith(".gz"):
        return gzip.open(path, mode)
    else:
        return open(path, mode)


def read_tsv(file, strip=True):
    """Read a tab separated file and return an iterator over rows."""
    start_time = datetime.now()
    log(f"read_tsv({file})")
    if isinstance(file, str):
        file = xopen(file, "rt")

    for i, line in enumerate(file):
        if i % 1_000_000 == 0:
            log(f"read_tsv {i:,}")
        if strip:
            line = line.strip()
        yield line.split("\t")
    minutes = (datetime.now() - start_time).seconds // 60
    log(f" read_tsv() processed {i:,} records in {minutes:,} minutes.")


def generate_cdump(data_file, date=None):
    """Generates cdump from a copy of data table.  If date is specified, only revisions
    created on or before that date will be considered.
    """
    logger.error(f"generate_cdump({data_file}, {date}) reading")
    # adding Z to the date will make sure all the timestamps are less than that date.
    #
    #   >>> "2010-05-17T10:20:30" < "2010-05-17"
    #   False
    #   >>> "2010-05-17T10:20:30" < "2010-05-17Z"
    #   True
    #
    # If scripts/oldump.sh has exported $OLDUMP_TESTING then save a lot of time by only
    # processing a subset of the lines in data_file.
    max_lines = 1_000_000 if os.getenv("OLDUMP_TESTING") else 0  # 0 means unlimited.
    filter = date and (lambda doc: doc["last_modified"]["value"] < date + "Z")
    print_dump(read_data_file(data_file, max_lines), filter=filter)


def sort_dump(dump_file=None, tmpdir="/tmp/", buffer_size="1G"):
    """Sort the given dump based on key."""
    start_time = datetime.now()
    tmpdir = os.path.join(tmpdir, "oldumpsort")
    if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)

    M = 1024 * 1024

    filenames = [os.path.join(tmpdir, "%02x.txt.gz" % i) for i in range(256)]
    files = [gzip.open(f, "wb") for f in filenames]
    stdin = xopen(dump_file, "rb") if dump_file else sys.stdin.buffer

    # split the file into 256 chunks using hash of key
    log("sort_dump", dump_file or "stdin")
    for i, line in enumerate(stdin):
        if i % 1_000_000 == 0:
            log(f"sort_dump {i:,}")

        type, key, revision, timestamp, json_data = line.strip().split(b"\t")
        findex = hash(key) % 256
        files[findex].write(line)

    for f in files:
        f.flush()
        f.close()
    files = []

    for fname in filenames:
        log("sort_dump", fname)
        status = os.system(
            "gzip -cd %(fname)s | sort -S%(buffer_size)s -k2,3" % locals()
        )
        if status != 0:
            raise Exception("sort failed with status %d" % status)
    minutes = (datetime.now() - start_time).seconds // 60
    log(f"sort_dump() processed {i:,} records in {minutes:,} minutes.")


def generate_dump(cdump_file=None):
    """Generate dump from cdump.

    The given cdump must be sorted by key.
    """

    def process(data):
        revision = lambda cols: int(cols[2])  # noqa: E731
        for key, rows in itertools.groupby(data, key=lambda cols: cols[1]):
            row = max(rows, key=revision)
            yield row

    start_time = datetime.now()
    tjoin = "\t".join
    data = read_tsv(cdump_file or sys.stdin, strip=False)
    # group by key and find the max by revision
    sys.stdout.writelines(tjoin(row) for row in process(data))
    minutes = (datetime.now() - start_time).seconds // 60
    log(f"generate_dump({cdump_file}) ran in {minutes:,} minutes.")


def generate_idump(day, **db_parameters):
    """Generate incremental dump for the given day."""
    db.setup_database(**db_parameters)
    rows = db.longquery(
        "SELECT data.* FROM data, version, transaction "
        + " WHERE data.thing_id=version.thing_id"
        + "     AND data.revision=version.revision"
        + "     AND version.transaction_id=transaction.id"
        + "     AND transaction.created >= $day"
        + "     AND transaction.created < date $day + interval '1 day'"
        + " ORDER BY transaction.created",
        vars=locals(),
        chunk_size=10_000,
    )
    print_dump(row.data for chunk in rows for row in chunk)


def split_dump(dump_file=None, format="oldump_%s.txt"):
    """Split dump into authors, editions and works."""
    log(f"split_dump({dump_file}, format={format})")
    start_time = datetime.now()
    types = ("/type/edition", "/type/author", "/type/work", "/type/redirect")
    files = {}
    for t in types:
        tname = t.split("/")[-1] + "s"
        files[t] = xopen(format % tname, "wt")

    stdin = xopen(dump_file, "rt") if dump_file else sys.stdin
    for i, line in enumerate(stdin):
        if i % 1_000_000 == 0:
            log(f"split_dump {i:,}")
        type, rest = line.split("\t", 1)
        if type in files:
            files[type].write(line)

    for f in files.values():
        f.close()
    minutes = (datetime.now() - start_time).seconds // 60
    log(f"split_dump() processed {i:,} records in {minutes:,} minutes.")


def make_index(dump_file):
    """Make index with "path", "title", "created" and "last_modified" columns."""
    log(f"make_index({dump_file})")
    start_time = datetime.now()
    for i, type, key, revision, timestamp, json_data in enumerate(read_tsv(dump_file)):
        data = json.loads(json_data)
        if type in ("/type/edition", "/type/work"):
            title = data.get("title", "untitled")
            path = key + "/" + urlsafe(title)
        elif type == "/type/author":
            title = data.get("name", "unnamed")
            path = key + "/" + urlsafe(title)
        else:
            title = data.get("title", key)
            path = key

        title = title.replace("\t", " ")

        if "created" in data:
            created = data["created"]["value"]
        else:
            created = "-"
        print("\t".join([web.safestr(path), web.safestr(title), created, timestamp]))
    minutes = (datetime.now() - start_time).seconds // 60
    log(f"make_index() processed {i:,} records in {minutes:,} minutes.")


def _process_key(key):
    mapping = {
        "/l/": "/languages/",
        "/a/": "/authors/",
        "/b/": "/books/",
        "/user/": "/people/",
    }
    for old, new in mapping.items():
        if key.startswith(old):
            return new + key[len(old) :]
    return key


def _process_data(data):
    """Convert keys from /a/, /b/, /l/ and /user/
    to /authors/, /books/, /languages/ and /people/ respectively."""
    if isinstance(data, list):
        return [_process_data(d) for d in data]
    elif isinstance(data, dict):
        if "key" in data:
            data["key"] = _process_key(data["key"])

        # convert date to ISO format
        if data.get("type") == "/type/datetime":
            data["value"] = data["value"].replace(" ", "T")

        return {k: _process_data(v) for k, v in data.items()}
    else:
        return data


def _make_sub(d):
    """Make substituter.

    >>> f = _make_sub(dict(a='aa', bb='b'))
    >>> f('aabbb')
    'aaaabb'
    """

    def f(a):
        return d[a.group(0)]

    rx = re.compile("|".join(re.escape(key) for key in d))
    return lambda s: s and rx.sub(f, s)


_pgdecode_dict = {r"\n": "\n", r"\r": "\r", r"\t": "\t", r"\\": "\\"}
_pgdecode = _make_sub(_pgdecode_dict)


def pgdecode(text):
    r"""Decode postgres encoded text.

    >>> pgdecode('\\n')
    '\n'
    """
    return _pgdecode(text)


def main(cmd, args):
    """Command Line interface for generating dumps."""
    iargs = iter(args)

    args = []
    kwargs = {}

    for a in iargs:
        if a.startswith("--"):
            name = a[2:].replace("-", "_")
            value = next(iargs)
            kwargs[name] = value
        else:
            args.append(a)

    func = {
        "cdump": generate_cdump,
        "dump": generate_dump,
        "idump": generate_idump,
        "sort": sort_dump,
        "split": split_dump,
        "index": make_index,
        "sitemaps": generate_sitemaps,
        "htmlindex": generate_html_index,
    }.get(cmd)
    if func:
        func(*args, **kwargs)
    else:
        logger.error(f"Unknown command: {cmd}")
        log(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
