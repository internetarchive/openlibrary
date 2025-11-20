"""Plugin to provide admin interface."""

import datetime
import json
import logging
import os
import socket
import subprocess
import sys
import traceback
from collections.abc import Iterable

import requests
import web
from internetarchive.exceptions import ItemLocateError

import openlibrary
from infogami import config
from infogami.plugins.api.code import jsonapi  # noqa: F401 side effects may be needed
from infogami.utils import delegate
from infogami.utils.context import context
from infogami.utils.view import add_flash_message, public, render
from openlibrary import accounts
from openlibrary.accounts.model import Account, OpenLibraryAccount, clear_cookies
from openlibrary.catalog.add_book import (
    create_ol_subjects_for_ocaid,
    update_ia_metadata_for_ol_edition,
)
from openlibrary.core import (
    admin as admin_stats,
)
from openlibrary.core import (
    cache,
    imports,
)
from openlibrary.core.models import Work
from openlibrary.plugins.openlibrary.pd import get_pd_dashboard_data
from openlibrary.plugins.upstream import forms, spamcheck

logger = logging.getLogger("openlibrary.admin")


def render_template(name, *a, **kw):
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return render[name](*a, **kw)


admin_tasks = []


def register_admin_page(path, cls, label=None, visible=True, librarians=False):
    label = label or cls.__name__
    t = web.storage(
        path=path, cls=cls, label=label, visible=visible, librarians=librarians
    )
    admin_tasks.append(t)


def revert_all_user_edits(account: Account) -> tuple[int, int]:
    """
    :return: tuple of (number of edits reverted, number of documents deleted)
    """
    i = 0
    edit_count = 0
    stop = False
    keys_to_delete = set()
    while not stop:
        changes = account.get_recentchanges(limit=100, offset=100 * i)
        added_records: list[list[dict]] = [
            c.changes for c in changes if c.kind == 'add-book'
        ]
        flattened_records: list[dict] = [
            record for lst in added_records for record in lst
        ]
        keys_to_delete |= {r['key'] for r in flattened_records}

        keys_to_revert: dict[str, list[int]] = {
            item.key: [] for change in changes for item in change.changes
        }
        for change in changes:
            for item in change.changes:
                keys_to_revert[item.key].append(change.id)

        deleted_keys = web.ctx.site.things(
            {'key': list(keys_to_revert), 'type': {'key': '/type/delete'}}
        )

        changesets_with_deleted_works = {
            change_id for key in deleted_keys for change_id in keys_to_revert[key]
        }

        changeset_ids = [
            c.id for c in changes if c.id not in changesets_with_deleted_works
        ]

        _, len_docs = revert_changesets(changeset_ids, "Reverted Spam")
        edit_count += len_docs
        i += 1
        if len(changes) < 100:
            stop = True

    delete_payload = [
        {'key': key, 'type': {'key': '/type/delete'}} for key in keys_to_delete
    ]
    web.ctx.site.save_many(delete_payload, 'Delete spam')
    return edit_count, len(delete_payload)


def revert_changesets(changeset_ids: Iterable[int], comment: str):
    """
    An aggressive revert function ; it rolls back all the documents to
    the revision that existed before the changeset was applied.
    Note this means that any edits made _after_ the given changeset will
    also be lost.
    """

    def get_doc(key: str, revision: int) -> dict:
        if revision == 0:
            return {"key": key, "type": {"key": "/type/delete"}}
        else:
            return web.ctx.site.get(key, revision).dict()

    site = web.ctx.site
    docs = [
        get_doc(c['key'], c['revision'] - 1)
        for cid in changeset_ids
        for c in site.get_change(cid).changes
    ]
    docs = [doc for doc in docs if doc.get('type', {}).get('key') != '/type/delete']
    data = {"reverted_changesets": [str(cid) for cid in changeset_ids]}
    manifest = web.ctx.site.save_many(docs, action="revert", data=data, comment=comment)
    return manifest, len(docs)


class admin(delegate.page):
    path = "/admin(?:/.*)?"

    def delegate(self):
        if web.ctx.path == "/admin":
            return self.handle(admin_index)

        for t in admin_tasks:
            m = web.re_compile('^' + t.path + '$').match(web.ctx.path)
            if m:
                return self.handle(t.cls, m.groups(), librarians=t.librarians)
        raise web.notfound()

    def handle(self, cls, args=(), librarians=False):
        # Use admin theme
        context.cssfile = "admin"

        m = getattr(cls(), web.ctx.method, None)
        if not m:
            raise web.nomethod(cls=cls)
        else:
            if (
                context.user
                and context.user.is_librarian()
                and web.ctx.path == '/admin/solr'
            ):
                return m(*args)
            if self.is_admin() or (
                librarians and context.user and context.user.is_super_librarian()
            ):
                return m(*args)
            else:
                return render.permission_denied(web.ctx.path, "Permission denied.")

    GET = POST = delegate

    def is_admin(self):
        """Returns True if the current user is in admin usergroup."""
        return context.user and context.user.key in [
            m.key for m in web.ctx.site.get('/usergroup/admin').members
        ]


class admin_index:
    def GET(self):
        return web.seeother('/stats')


class gitpull:
    def GET(self):
        root = os.path.join(os.path.dirname(openlibrary.__file__), os.path.pardir)
        root = os.path.normpath(root)

        p = subprocess.Popen(
            'cd %s && git pull' % root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        out = p.stdout.read()
        p.wait()
        return '<pre>' + web.websafe(out) + '</pre>'


class reload:
    def GET(self):
        if servers := config.get("plugin_admin", {}).get("webservers", []):
            body = "".join(self.reload(servers))
        else:
            body = "No webservers specified in the configuration file."

        return render_template("message", "Reload", body)

    def reload(self, servers):
        for s in servers:
            s = web.rstrips(s, "/") + "/_reload"
            yield "<h3>" + s + "</h3>"
            try:
                response = requests.get(s).text
                yield "<p><pre>" + response[:100] + "</pre></p>"
            except:
                yield "<p><pre>%s</pre></p>" % traceback.format_exc()


@web.memoize
def local_ip():

    return socket.gethostbyname(socket.gethostname())


class _reload(delegate.page):
    def GET(self):
        # make sure the request is coming from the LAN.
        if (
            web.ctx.ip not in ['127.0.0.1', '0.0.0.0']
            and web.ctx.ip.rsplit(".", 1)[0] != local_ip().rsplit(".", 1)[0]
        ):
            return render.permission_denied(
                web.ctx.fullpath, "Permission denied to reload templates/macros."
            )

        from infogami.plugins.wikitemplates import (  # noqa: PLC0415
            code as wikitemplates,
        )

        wikitemplates.load_all()

        from openlibrary.plugins.upstream import code as upstream  # noqa: PLC0415

        upstream.reload()
        return delegate.RawText("done")


class any:
    def GET(self):
        pass


class people:
    def GET(self):
        i = web.input(email=None, ia_id=None)

        account = None
        if i.email:
            account = accounts.find(email=i.email)
        if i.ia_id:
            account = OpenLibraryAccount.get_by_link(i.ia_id)
        if account:
            raise web.seeother(f"/admin/people/{account.username}")
        return render_template("admin/people/index", email=i.email, ia_id=i.ia_id)


class add_work_to_staff_picks:
    def GET(self):
        return render_template("admin/sync")

    def POST(self):
        i = web.input(action="add", work_id='', subjects='openlibrary_staff_picks')
        results = {}
        work_ids = i.work_id.split(',')
        subjects = i.subjects.split(',')
        for work_id in work_ids:
            work = web.ctx.site.get('/works/%s' % work_id)
            editions = work.editions
            ocaids = [edition.ocaid for edition in editions if edition.ocaid]
            results[work_id] = {}
            for ocaid in ocaids:
                try:
                    results[work_id][ocaid] = create_ol_subjects_for_ocaid(
                        ocaid, subjects=subjects
                    )
                except ItemLocateError as err:
                    results[work_id][
                        ocaid
                    ] = f'Failed to add to staff picks. Error message: {err}'

        return delegate.RawText(json.dumps(results), content_type="application/json")


class resolve_redirects:
    def GET(self):
        return self.main(test=True)

    def POST(self):
        return self.main(test=False)

    def main(self, test=False):
        params = web.input(key='', test='')

        # Provide an escape hatch to let GET requests resolve
        if test is True and params.test == 'false':
            test = False

        # Provide an escape hatch to let POST requests preview
        elif test is False and params.test:
            test = True

        summary = Work.resolve_redirect_chain(params.key, test=test)

        return delegate.RawText(json.dumps(summary), content_type="application/json")


class sync_ol_ia:
    def GET(self):
        """Updates an Open Library edition's Archive.org item by writing its
        latest openlibrary_work and openlibrary_edition to the
        Archive.org item's metadata.
        """
        i = web.input(edition_id='')
        data = update_ia_metadata_for_ol_edition(i.edition_id)
        return delegate.RawText(json.dumps(data), content_type="application/json")


class people_view:
    def GET(self, key):
        account = accounts.find(username=key) or accounts.find(email=key)
        if account:
            if "@" in key:
                raise web.seeother("/admin/people/" + account.username)
            else:
                return render_template('admin/people/view', account)
        else:
            raise web.notfound()

    def POST(self, key):
        user = accounts.find(username=key)
        if not user:
            raise web.notfound()

        i = web.input(action=None, tag=None, bot=None, dry_run=None)
        if i.action == "update_email":
            return self.POST_update_email(user, i)
        elif i.action == "update_password":
            return self.POST_update_password(user, i)
        elif i.action == "resend_link":
            return self.POST_resend_link(user)
        elif i.action == "activate_account":
            return self.POST_activate_account(user)
        elif i.action == "block_account":
            return self.POST_block_account(user)
        elif i.action == "block_account_and_revert":
            return self.POST_block_account_and_revert(user)
        elif i.action == "unblock_account":
            return self.POST_unblock_account(user)
        elif i.action == "add_tag":
            return self.POST_add_tag(user, i.tag)
        elif i.action == "remove_tag":
            return self.POST_remove_tag(user, i.tag)
        elif i.action == "set_bot_flag":
            return self.POST_set_bot_flag(user, i.bot)
        elif i.action == "su":
            return self.POST_su(user)
        elif i.action == "anonymize_account":
            test = bool(i.dry_run)
            return self.POST_anonymize_account(user, test)
        else:
            raise web.seeother(web.ctx.path)

    def POST_activate_account(self, user):
        user.activate()
        raise web.seeother(web.ctx.path)

    def POST_block_account(self, account):
        account.block()
        raise web.seeother(web.ctx.path)

    def POST_block_account_and_revert(self, account: Account):
        account.block()
        edit_count, deleted_count = revert_all_user_edits(account)
        add_flash_message(
            "info",
            f"Blocked the account and reverted all {edit_count} edits. {deleted_count} records deleted.",
        )
        raise web.seeother(web.ctx.path)

    def POST_unblock_account(self, account):
        account.unblock()
        raise web.seeother(web.ctx.path)

    def POST_resend_link(self, user):
        key = "account/%s/verify" % user.username
        activation_link = web.ctx.site.store.get(key)
        del activation_link
        user.send_verification_email()
        add_flash_message("info", "Activation mail has been resent.")
        raise web.seeother(web.ctx.path)

    def POST_update_email(self, account, i):
        user = account.get_user()
        if not forms.vemail.valid(i.email):
            return render_template(
                "admin/people/view", user, i, {"email": forms.vemail.msg}
            )

        if not forms.email_not_already_used.valid(i.email):
            return render_template(
                "admin/people/view",
                user,
                i,
                {"email": forms.email_not_already_used.msg},
            )

        account.update_email(i.email)

        add_flash_message("info", "Email updated successfully!")
        raise web.seeother(web.ctx.path)

    def POST_update_password(self, account, i):
        user = account.get_user()
        if not forms.vpass.valid(i.password):
            return render_template(
                "admin/people/view", user, i, {"password": forms.vpass.msg}
            )

        account.update_password(i.password)

        logger.info("updated password of %s", user.key)
        add_flash_message("info", "Password updated successfully!")
        raise web.seeother(web.ctx.path)

    def POST_add_tag(self, account, tag):
        account.add_tag(tag)
        return delegate.RawText('{"ok": "true"}', content_type="application/json")

    def POST_remove_tag(self, account, tag):
        account.remove_tag(tag)
        return delegate.RawText('{"ok": "true"}', content_type="application/json")

    def POST_set_bot_flag(self, account, bot):
        bot = (bot and bot.lower()) == "true"
        account.set_bot_flag(bot)
        raise web.seeother(web.ctx.path)

    def POST_su(self, account):
        code = account.generate_login_code()
        # Clear all existing admin cookies before logging in as another user
        clear_cookies()
        web.setcookie(config.login_cookie_name, code, expires="")

        return web.seeother("/")

    def POST_anonymize_account(self, account, test):
        results = account.anonymize(test=test)
        msg = (
            f"Account anonymized. New username: {results['new_username']}. "
            f"Notes deleted: {results['booknotes_count']}. "
            f"Ratings updated: {results['ratings_count']}. "
            f"Observations updated: {results['observations_count']}. "
            f"Bookshelves updated: {results['bookshelves_count']}."
            f"Merge requests updated: {results['merge_request_count']}"
        )
        add_flash_message("info", msg)
        raise web.seeother(web.ctx.path)


class people_edits:
    def GET(self, username):
        account = accounts.find(username=username)
        if not account:
            raise web.notfound()
        else:
            return render_template("admin/people/edits", account)

    def POST(self, username):
        i = web.input(changesets=[], comment="Revert", action="revert")
        if i.action == "revert" and i.changesets:
            revert_changesets(i.changesets, i.comment)
        raise web.redirect(web.ctx.path)


class ipaddress:
    def GET(self):
        return render_template('admin/ip/index')


class ipaddress_view:
    def GET(self, ip):
        return render_template('admin/ip/view', ip)

    def POST(self, ip):
        i = web.input(changesets=[], comment="Revert", action="revert")
        if i.action == "block":
            self.block(ip)
        else:
            revert_changesets(i.changesets, i.comment)
        raise web.redirect(web.ctx.path)

    def block(self, ip):
        ips = get_blocked_ips()
        if ip not in ips:
            ips.append(ip)
        block().block_ips(ips)


class stats:
    def GET(self, today):
        json = web.ctx.site._conn.request(
            web.ctx.site.name, '/get', 'GET', {'key': '/admin/stats/' + today}
        )
        return delegate.RawText(json)

    def POST(self, today):
        """Update stats for today."""
        doc = self.get_stats(today)
        doc._save()
        raise web.seeother(web.ctx.path)

    def get_stats(self, today):
        stats = web.ctx.site._request("/stats/" + today)

        key = '/admin/stats/' + today
        doc = web.ctx.site.new(key, {'key': key, 'type': {'key': '/type/object'}})
        doc.edits = {
            'human': stats.edits - stats.edits_by_bots,
            'bot': stats.edits_by_bots,
            'total': stats.edits,
        }
        doc.members = stats.new_accounts
        return doc


class block:
    def GET(self):
        page = web.ctx.site.get("/admin/block") or web.storage(
            ips=[web.storage(ip="127.0.0.1", duration="1 week", since="1 day")]
        )
        return render_template("admin/block", page)

    def POST(self):
        i = web.input()
        ips = [ip.strip() for ip in i.ips.splitlines()]
        self.block_ips(ips)
        add_flash_message("info", "Saved!")
        raise web.seeother("/admin/block")

    def block_ips(self, ips):
        page = web.ctx.get("/admin/block") or web.ctx.site.new(
            "/admin/block", {"key": "/admin/block", "type": "/type/object"}
        )
        page.ips = [{'ip': ip} for ip in ips]
        page._save("updated blocked IPs")


def get_blocked_ips():
    if doc := web.ctx.site.get("/admin/block"):
        return [d.ip for d in doc.ips]
    else:
        return []


def block_ip_processor(handler):
    if (
        not web.ctx.path.startswith("/admin")
        and (web.ctx.method == "POST" or web.ctx.path.endswith("/edit"))
        and web.ctx.ip in get_blocked_ips()
    ):
        return render_template(
            "permission_denied", web.ctx.path, "Your IP address is blocked."
        )
    else:
        return handler()


def daterange(date, *slice):
    return [date + datetime.timedelta(i) for i in range(*slice)]


def storify(d):
    if isinstance(d, dict):
        return web.storage((k, storify(v)) for k, v in d.items())
    elif isinstance(d, list):
        return [storify(v) for v in d]
    else:
        return d


def get_counts():
    """Generate counts for various operations which will be given to the
    index page"""
    retval = admin_stats.get_stats(100)
    return storify(retval)


def get_admin_stats():
    def f(dates):
        keys = ["/admin/stats/" + date.isoformat() for date in dates]
        docs = web.ctx.site.get_many(keys)
        return g(docs)

    def has_doc(date):
        return bool(web.ctx.site.get('/admin/stats/' + date.isoformat()))

    def g(docs):
        return {
            'edits': {
                'human': sum(doc['edits']['human'] for doc in docs),
                'bot': sum(doc['edits']['bot'] for doc in docs),
                'total': sum(doc['edits']['total'] for doc in docs),
            },
            'members': sum(doc['members'] for doc in docs),
        }

    date = datetime.datetime.utcnow().date()

    if has_doc(date):
        today = f([date])
    else:
        today = g([stats().get_stats(date.isoformat())])
    yesterday = f(daterange(date, -1, 0, 1))
    thisweek = f(daterange(date, 0, -7, -1))
    thismonth = f(daterange(date, 0, -30, -1))

    xstats = {
        'edits': {
            'today': today['edits'],
            'yesterday': yesterday['edits'],
            'thisweek': thisweek['edits'],
            'thismonth': thismonth['edits'],
        },
        'members': {
            'today': today['members'],
            'yesterday': yesterday['members'],
            'thisweek': thisweek['members'],
            'thismonth': thismonth['members'],
        },
    }
    return storify(xstats)


from openlibrary.plugins.upstream import borrow  # noqa: F401 side effects may be needed


class inspect:
    def GET(self, section):
        if section == "/store":
            return self.GET_store()
        elif section == "/memcache":
            return self.GET_memcache()
        else:
            raise web.notfound()

    def GET_store(self):
        i = web.input(key=None, type=None, name=None, value=None)

        if i.key:
            doc = web.ctx.site.store.get(i.key)
            if doc:
                docs = [doc]
            else:
                docs = []
        else:
            docs = web.ctx.site.store.values(
                type=i.type or None,
                name=i.name or None,
                value=i.value or None,
                limit=100,
            )

        return render_template("admin/inspect/store", docs, input=i)

    def GET_memcache(self):
        i = web.input(action="read")
        i.setdefault("keys", "")

        mc = cache.get_memcache().memcache

        keys = [k.strip() for k in i["keys"].split() if k.strip()]
        if i.action == "delete":
            mc.delete_multi(keys)
            add_flash_message("info", "Deleted %s keys from memcache" % len(keys))
            return render_template("admin/inspect/memcache", [], {})
        else:
            mapping = keys and mc.get_multi(keys)
            return render_template("admin/inspect/memcache", keys, mapping)


class spamwords:
    def GET(self):
        spamwords = spamcheck.get_spam_words()
        domains = spamcheck.get_spam_domains()
        return render_template("admin/spamwords.html", spamwords, domains)

    def POST(self):
        i = web.input(spamwords="", domains="", action="")
        if i.action == "save-spamwords":
            spamcheck.set_spam_words(i.spamwords.strip().split("\n"))
            add_flash_message("info", "Updated spam words successfully.")
        elif i.action == "save-domains":
            spamcheck.set_spam_domains(i.domains.strip().split("\n"))
            add_flash_message("info", "Updated domains successfully.")
        raise web.redirect("/admin/spamwords")


class _graphs:
    def GET(self):
        return render_template("admin/graphs")


class permissions:
    def GET(self):
        perm_pages = self.get_permission("/")
        # assuming that the permission of books and authors is same as works
        perm_records = self.get_permission("/works")
        return render_template("admin/permissions", perm_records, perm_pages)

    def get_permission(self, key):
        doc = web.ctx.site.get(key)
        perm = doc and doc.child_permission
        return (perm and perm.key) or "/permission/open"

    def set_permission(self, key, permission):
        """Returns the doc with permission set.
        The caller must save the doc.
        """
        doc = web.ctx.site.get(key)
        doc = (doc and doc.dict()) or {"key": key, "type": {"key": "/type/page"}}

        # so that only admins can modify the permission
        doc["permission"] = {"key": "/permission/restricted"}

        doc["child_permission"] = {"key": permission}
        return doc

    def POST(self):
        i = web.input(
            perm_pages="/permission/loggedinusers",
            perm_records="/permission/loggedinusers",
        )

        root = self.set_permission("/", i.perm_pages)
        works = self.set_permission("/works", i.perm_records)
        books = self.set_permission("/books", i.perm_records)
        authors = self.set_permission("/authors", i.perm_records)
        web.ctx.site.save_many(
            [root, works, books, authors], comment="Updated edit policy."
        )

        add_flash_message("info", "Edit policy has been updated!")
        return self.GET()


class attach_debugger:
    def GET(self):
        python_version = "{}.{}.{}".format(*sys.version_info)
        return render_template("admin/attach_debugger", python_version)

    def POST(self):
        import debugpy  # noqa: PLC0415, T100

        # Allow other computers to attach to ptvsd at this IP address and port.
        web.debug("Enabling debugger attachment")
        debugpy.listen(('0.0.0.0', 3000))  # noqa: T100
        web.debug("Waiting for debugger to attach...")
        debugpy.wait_for_client()  # noqa: T100
        web.debug("Debugger attached to port 3000")
        add_flash_message("info", "Debugger attached!")

        return self.GET()


class solr:
    def GET(self):
        return render_template("admin/solr")

    def POST(self):
        i = web.input(keys="")
        keys = i['keys'].strip().split()
        web.ctx.site.store['solr-force-update'] = {
            "type": "solr-force-update",
            "keys": keys,
            "_rev": None,
        }
        add_flash_message("info", "Added the specified keys to solr update queue.!")
        return self.GET()


class imports_home:
    def GET(self):
        return render_template("admin/imports", imports.Stats)


class imports_public(delegate.page):
    path = "/imports"

    def GET(self):
        return imports_home().GET()


class imports_add:
    def GET(self):
        return render_template("admin/imports-add")

    def POST(self):
        i = web.input("identifiers")
        identifiers = [
            line.strip() for line in i.identifiers.splitlines() if line.strip()
        ]
        batch_name = "admin"
        batch = imports.Batch.find(batch_name, create=True)
        batch.add_items(identifiers)
        add_flash_message("info", "Added the specified identifiers to import queue.")
        raise web.seeother("/admin/imports")


class imports_by_date:
    def GET(self, date):
        return render_template("admin/imports_by_date", imports.Stats(), date)


class show_log:
    def GET(self):
        i = web.input(name='')
        logname = i.name
        filepath = config.get('errorlog', 'errors') + '/' + logname + '.html'
        if os.path.exists(filepath):
            with open(filepath) as f:
                return f.read()


class pd_dashboard:
    def GET(self):
        dashboard_data = get_pd_dashboard_data()

        return render_template("admin/pd_dashboard", dashboard_data)


def setup():
    register_admin_page('/admin/git-pull', gitpull, label='git-pull')
    register_admin_page('/admin/reload', reload, label='Reload Templates')
    register_admin_page('/admin/people', people, label='People')
    register_admin_page('/admin/people/([^/]*)', people_view, label='View People')
    register_admin_page('/admin/people/([^/]*)/edits', people_edits, label='Edits')
    register_admin_page('/admin/ip', ipaddress, label='IP')
    register_admin_page('/admin/ip/(.*)', ipaddress_view, label='View IP')
    register_admin_page(r'/admin/stats/(\d\d\d\d-\d\d-\d\d)', stats, label='Stats JSON')
    register_admin_page('/admin/block', block, label='')
    register_admin_page(
        '/admin/attach_debugger', attach_debugger, label='Attach Debugger'
    )
    register_admin_page('/admin/inspect(?:(/.+))?', inspect, label="")
    register_admin_page('/admin/graphs', _graphs, label="")
    register_admin_page('/admin/logs', show_log, label="")
    register_admin_page('/admin/permissions', permissions, label="")
    register_admin_page('/admin/solr', solr, label="", librarians=True)
    register_admin_page('/admin/sync', sync_ol_ia, label="", librarians=True)
    register_admin_page(
        '/admin/resolve_redirects', resolve_redirects, label="Resolve Redirects"
    )

    register_admin_page(
        '/admin/staffpicks', add_work_to_staff_picks, label="", librarians=True
    )

    register_admin_page('/admin/imports', imports_home, label="")
    register_admin_page('/admin/imports/add', imports_add, label="")
    register_admin_page(
        r'/admin/imports/(\d\d\d\d-\d\d-\d\d)', imports_by_date, label=""
    )
    register_admin_page('/admin/spamwords', spamwords, label="")
    register_admin_page("/admin/pd", pd_dashboard)

    from openlibrary.plugins.admin import mem  # noqa: PLC0415

    for p in [mem._memory, mem._memory_type, mem._memory_id]:
        register_admin_page('/admin' + p.path, p)

    public(get_admin_stats)
    public(get_blocked_ips)
    delegate.app.add_processor(block_ip_processor)

    from openlibrary.plugins.admin import graphs  # noqa: PLC0415

    graphs.setup()


setup()
