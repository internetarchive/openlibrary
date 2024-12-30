"""Merge authors.
"""

import json
import re
from typing import Any

import web

from infogami.infobase.client import ClientException
from infogami.utils import delegate
from infogami.utils.view import render_template, safeint
from openlibrary.accounts import get_current_user
from openlibrary.plugins.upstream.edits import process_merge_request
from openlibrary.plugins.worksearch.code import top_books_from_author
from openlibrary.utils import dicthash, uniq


class BasicRedirectEngine:
    """
    Creates redirects whilst updating any references to the now-defunct record to point
    to the newly identified canonical record.
    """

    def make_redirects(self, master: str, duplicates: list[str]) -> list[dict]:
        # Create the actual redirect objects
        docs_to_save = [make_redirect_doc(key, master) for key in duplicates]

        # find the references of each duplicate and convert them
        references = self.find_all_references(duplicates)
        docs = get_many(references)
        docs_to_save.extend(
            self.update_references(doc, master, duplicates) for doc in docs
        )
        return docs_to_save

    def find_references(self, key):
        """
        Returns keys of all the docs which have a reference to the given key.
        All the subclasses must provide an implementation for this method.
        :param str key: e.g. /works/OL1W
        :rtype: list of str
        """
        raise NotImplementedError()

    def find_all_references(self, keys):
        refs = {ref for key in keys for ref in self.find_references(key)}
        return list(refs)

    def update_references(self, doc: Any, master: str, duplicates: list[str]) -> Any:
        """
        Converts references to any of the duplicates in the given doc to the master.
        """
        if isinstance(doc, dict):
            if list(doc) == ['key']:
                return {"key": master} if doc['key'] in duplicates else doc
            else:
                return {
                    k: self.update_references(v, master, duplicates)
                    for k, v in doc.items()
                }
        elif isinstance(doc, list):
            values = [self.update_references(v, master, duplicates) for v in doc]
            return uniq(values, key=dicthash)
        else:
            return doc


class BasicMergeEngine:
    """
    Generic merge functionality useful for all types of merges.
    """

    def __init__(self, redirect_engine):
        """
        :param BasicRedirectEngine redirect_engine:
        """
        self.redirect_engine = redirect_engine

    def merge(self, master, duplicates):
        docs = self.do_merge(master, duplicates)
        return self.save(docs, master, duplicates)

    def do_merge(self, master: str, duplicates: list[str]) -> list:
        """
        Performs the merge and returns the list of docs to save.
        :param str master: key of master doc
        :param list of str duplicates: keys of duplicates
        :return: Document to save
        """
        docs_to_save = []
        docs_to_save.extend(self.redirect_engine.make_redirects(master, duplicates))

        # Merge all the duplicates into the master.
        master_doc = web.ctx.site.get(master).dict()
        dups = get_many(duplicates)
        for d in dups:
            master_doc = self.merge_docs(master_doc, d)

        docs_to_save.append(master_doc)
        return docs_to_save

    def save(self, docs, master, duplicates):
        """Saves the effected docs because of merge.

        All the subclasses must provide an implementation for this method.
        """
        raise NotImplementedError()

    def merge_docs(self, master, dup):
        """Merge duplicate doc into master doc."""
        keys = set(list(master) + list(dup))
        return {k: self.merge_property(master.get(k), dup.get(k)) for k in keys}

    def merge_property(self, a, b):
        if isinstance(a, list) and isinstance(b, list):
            return uniq(a + b, key=dicthash)
        elif not a:
            return b
        else:
            return a


class AuthorRedirectEngine(BasicRedirectEngine):
    def find_references(self, key):
        q = {"type": "/type/edition", "authors": key, "limit": 10000}
        edition_keys = web.ctx.site.things(q)
        editions = get_many(edition_keys)
        work_keys_1 = [w['key'] for e in editions for w in e.get('works', [])]

        q = {"type": "/type/work", "authors": {"author": {"key": key}}, "limit": 10000}
        work_keys_2 = web.ctx.site.things(q)
        return edition_keys + work_keys_1 + work_keys_2


class AuthorMergeEngine(BasicMergeEngine):
    def merge_docs(self, master, dup):
        # avoid merging other types.
        if dup['type']['key'] == '/type/author':
            master = BasicMergeEngine.merge_docs(self, master, dup)
            if dup.get('name') and not name_eq(dup['name'], master.get('name') or ''):
                master.setdefault('alternate_names', []).append(dup['name'])
            if 'alternate_names' in master:
                master['alternate_names'] = uniq(
                    master['alternate_names'], key=space_squash_and_strip
                )
        return master

    def save(self, docs, master, duplicates):
        # There is a bug (#89) due to which old revisions of the docs are being sent to
        # save. Collecting all the possible information to detect the problem and
        # saving it in datastore. See that data here:
        # https://openlibrary.org/admin/inspect/store?type=merge-authors-debug&name=bad_merge&value=true
        mc = self._get_memcache()
        debug_doc = {
            'type': 'merge-authors-debug',
            'memcache': mc
            and {
                k: json.loads(v)
                for k, v in mc.get_multi([doc['key'] for doc in docs]).items()
            },
            'docs': docs,
        }

        result = web.ctx.site.save_many(
            docs,
            comment='merge authors',
            action="merge-authors",
            data={"master": master, "duplicates": list(duplicates)},
        )
        before_revs = {doc['key']: doc.get('revision') for doc in docs}
        after_revs = {row['key']: row['revision'] for row in result}

        # Bad merges are happening when we are getting non-recent docs. That can be
        # identified by checking difference in the revision numbers before/after save
        bad_merge = any(
            after_revs[key] > before_revs[key] + 1
            for key in after_revs
            if before_revs[key] is not None
        )

        debug_doc['bad_merge'] = str(bad_merge).lower()
        debug_doc['result'] = result
        key = 'merge_authors/%d' % web.ctx.site.seq.next_value('merge-authors-debug')
        web.ctx.site.store[key] = debug_doc

        return result

    def _get_memcache(self):
        from openlibrary.plugins.openlibrary import connection

        return connection._memcache


re_whitespace = re.compile(r'\s+')


def space_squash_and_strip(s):
    return re_whitespace.sub(' ', s).strip()


def name_eq(n1, n2):
    return space_squash_and_strip(n1) == space_squash_and_strip(n2)


def fix_table_of_contents(table_of_contents: list[str | dict]) -> list:
    """
    Some books have bad table_of_contents--convert them in to correct format.
    """

    def row(r):
        if isinstance(r, str):
            level = 0
            label = ""
            title = web.safeunicode(r)
            pagenum = ""
        elif 'value' in r:
            level = 0
            label = ""
            title = web.safeunicode(r['value'])
            pagenum = ""
        else:
            level = safeint(r.get('level', '0'), 0)
            label = r.get('label', '')
            title = r.get('title', '')
            pagenum = r.get('pagenum', '')

        r = web.storage(level=level, label=label, title=title, pagenum=pagenum)
        return r

    return [row for row in map(row, table_of_contents) if any(row.values())]


def get_many(keys: list[str]) -> list[dict]:
    def process(doc):
        # some books have bad table_of_contents. Fix them to avoid failure on save.
        if doc['type']['key'] == "/type/edition" and 'table_of_contents' in doc:
            doc['table_of_contents'] = fix_table_of_contents(doc['table_of_contents'])
        return doc

    return [process(thing.dict()) for thing in web.ctx.site.get_many(list(keys))]


def make_redirect_doc(key, redirect):
    return {"key": key, "type": {"key": "/type/redirect"}, "location": redirect}


class merge_authors(delegate.page):
    path = '/authors/merge'

    def is_enabled(self):
        user = web.ctx.site.get_user()
        return "merge-authors" in web.ctx.features or (user and user.is_admin())

    def filter_authors(self, keys):
        docs = web.ctx.site.get_many(["/authors/" + k for k in keys])
        d = {doc.key: doc.type.key for doc in docs}
        return [k for k in keys if d.get("/authors/" + k) == '/type/author']

    def GET(self):
        i = web.input(key=[], mrid=None, records='')

        # key is deprecated in favor of records but we will support both
        if deprecated_keys := uniq(i.key):
            redir_url = f'/authors/merge/?records={",".join(deprecated_keys)}'
            raise web.redirect(redir_url)

        keys = uniq(i.records.strip(',').split(','))

        # filter bad keys
        keys = self.filter_authors(keys)

        # sort keys by lowest OL number
        keys = sorted(keys, key=lambda key: int(key[2:-1]))

        user = get_current_user()
        can_merge = user and (user.is_admin() or user.is_super_librarian())
        return render_template(
            'merge/authors',
            keys,
            top_books_from_author=top_books_from_author,
            mrid=i.mrid,
            can_merge=can_merge,
        )

    def POST(self):
        i = web.input(key=[], master=None, merge_key=[], mrid=None, comment=None)
        keys = uniq(i.key)
        selected = uniq(i.merge_key)

        user = get_current_user()
        can_merge = user and (user.is_admin() or user.is_super_librarian())
        can_request_merge = not can_merge and (user and user.is_librarian())

        # filter bad keys
        keys = self.filter_authors(keys)

        # doesn't make sense to merge master with it self.
        if i.master in selected:
            selected.remove(i.master)

        formdata = web.storage(master=i.master, selected=selected)

        if not i.master or len(selected) == 0:
            return render_template(
                "merge/authors",
                keys,
                top_books_from_author=top_books_from_author,
                formdata=formdata,
                mrid=i.mrid,
            )
        elif can_request_merge:
            # Create merge author request:
            selected.insert(0, i.master)
            data = {
                'mr_type': 2,
                'action': 'create-pending',
                'olids': ','.join(selected),
            }

            if i.comment:
                data['comment'] = i.comment

            result = process_merge_request('create-request', data)
            mrid = result.get('id', None)

            username = user.get('key').split('/')[-1]

            redir_url = f'/merges?submitter={username}'
            if mrid:
                redir_url = f'{redir_url}#mrid-{mrid}'

            raise web.seeother(redir_url)
        else:
            # redirect to the master. The master will display a progressbar and call the merge_authors_json to trigger the merge.
            redir_url = (
                f'/authors/{i.master}/-/?merge=true&duplicates={",".join(selected)}'
            )
            if i.mrid:
                redir_url = f'{redir_url}&mrid={i.mrid}'
            if i.comment:
                redir_url = f'{redir_url}&comment={i.comment}'
            raise web.seeother(redir_url)


class merge_authors_json(delegate.page):
    """JSON API for merge authors.

    This is called from the master author page to trigger the merge while displaying progress.
    """

    path = "/authors/merge"
    encoding = "json"

    def is_enabled(self):
        user = web.ctx.site.get_user()
        return "merge-authors" in web.ctx.features or (user and user.is_admin())

    def POST(self):
        data = json.loads(web.data())
        master = data['master']
        duplicates = data['duplicates']
        mrid = data.get('mrid', None)
        comment = data.get('comment', None)
        olids = data.get('olids', '')

        engine = AuthorMergeEngine(AuthorRedirectEngine())
        try:
            result = engine.merge(master, duplicates)
            if mrid:
                # Update the request
                rtype = 'update-request'
                data = {'action': 'approve', 'mrid': mrid}
            else:
                # Create new request
                rtype = 'create-request'
                data = {'mr_type': 2, 'olids': olids, 'action': 'create-merged'}
            if comment:
                data['comment'] = comment
            process_merge_request(rtype, data)
        except ClientException as e:
            raise web.badrequest(json.loads(e.json))
        return delegate.RawText(json.dumps(result), content_type="application/json")


def setup():
    pass
