"""Librarian Deletes"""


import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue


def response(status='ok', **kwargs):
    return {'status': status, **kwargs}

class community_deletes:
    """Handler for deletion requests"""

    @staticmethod
    def delete_request(
        username,
        action='',
        mr_type=None,
        olids='',
        comment: str | None = None,
    ):
        def is_valid_action(action):
            valid = action in ('create-pending', 'create-merged')
            return valid

        if is_valid_action(action):
            olid_list = olids.split(',')

            title = community_deletes.create_title(mr_type, olid_list)
            url = community_deletes.create_url(mr_type, olid_list)
            
            if action == 'create-pending':
                result = CommunityEditsQueue.submit_request(
                    url, username, title=title, comment=comment, mr_type=mr_type
                )
            elif action == 'create-merged':
                result = CommunityEditsQueue.submit_request(
                    url,
                    username,
                    title=title,
                    comment=comment,
                    reviewer=username,
                    status=CommunityEditsQueue.STATUS['MERGED'],
                    mr_type=mr_type,
                )
            
            resp = (
                response(id=result)
                if result
                else response(status='error', error='Request creation failed.')
            )
        else:
            resp = response(
                status='error',
                error=f'Action "{action}" is invalid for this request type.',
            )

        return resp

    @staticmethod
    def create_url(mr_type: int, olids: list[str], primary: str | None = None) -> str:
        if mr_type == CommunityEditsQueue.TYPE['DELETION']:
            # Bulk deletion page for works (and possibly other record types later)
            return f'/works/delete?records={",".join(olids)}'
        return ''

    @staticmethod
    def create_title(mr_type: int, olids: list[str]) -> str:
        if mr_type == CommunityEditsQueue.TYPE['DELETION'] and olids:
            # Single deletion type - check all entity types
            olid = olids[0]
            # Try work first
            record = web.ctx.site.get(f'/works/{olid}')
            if not record:
                # Try edition
                record = web.ctx.site.get(f'/books/{olid}')
            if not record:
                # Try author
                record = web.ctx.site.get(f'/authors/{olid}')
            if record:
                return (
                    getattr(record, 'title', None)
                    or getattr(record, 'name', None)
                    or 'Unknown record'
                )
        return 'Unknown record'


class works_delete_page(delegate.page):
    path = '/works/delete'

    def GET(self):
        i = web.input(records='', mrid=None)

        if not i.records:
            raise web.notfound("No works provided")

        olids = [olid for olid in i.records.split(',') if olid]

        works = []
        for olid in olids:
            rec = web.ctx.site.get(f'/works/{olid}')
            if rec:
                works.append(rec)

        user = accounts.get_current_user()
        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True

        return render_template(
            'delete_ile/delete_works',
            works,
            ",".join(olids),
            i.mrid,
            can_delete,
        )

    def POST(self):
        i = web.input(records='', comment='', mrid=None)

        user = accounts.get_current_user()
        if not user:
            raise web.seeother('/account/login')

        username = user['key'].split('/')[-1]

        resp = community_deletes.delete_request(
            username=username,
            action='create-pending',
            mr_type=CommunityEditsQueue.TYPE['DELETION'],
            olids=i.records,
            comment=i.comment or None,
        )

        if resp.get('status') == 'error':
            return response(status="error", error=resp.get("error"))

        olids = [olid for olid in i.records.split(',') if olid]
        works = [web.ctx.site.get(f'/works/{olid}') for olid in olids if web.ctx.site.get(f'/works/{olid}')]

        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True

        return render_template(
            'delete_ile/delete_works',
            works,
            ",".join(olids),
            i.mrid,
            can_delete,
        )


class authors_delete_page(delegate.page):
    path = '/authors/delete'

    def GET(self):
        i = web.input(records='', mrid=None)

        if not i.records:
            raise web.notfound("No authors provided")

        olids = [olid for olid in i.records.split(',') if olid]

        authors = []
        for olid in olids:
            rec = web.ctx.site.get(f'/authors/{olid}')
            if rec:
                authors.append(rec)

        user = accounts.get_current_user()
        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True

        return render_template(
            'delete_ile/delete_authors',
            authors,
            ",".join(olids),
            i.mrid,
            can_delete,
        )

    def POST(self):
        i = web.input(records='', comment='', mrid=None)

        user = accounts.get_current_user()
        if not user:
            raise web.seeother('/account/login')

        username = user['key'].split('/')[-1]

        resp = community_deletes.delete_request(
            username=username,
            action='create-pending',
            mr_type=CommunityEditsQueue.TYPE['DELETION'],
            olids=i.records,
            comment=i.comment or None,
        )

        if resp.get('status') == 'error':
            return response(status="error", error=resp.get("error"))

        olids = [olid for olid in i.records.split(',') if olid]
        authors = [web.ctx.site.get(f'/authors/{olid}') for olid in olids if web.ctx.site.get(f'/authors/{olid}')]

        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True

        return render_template(
            'delete_ile/delete_authors',
            authors,
            ",".join(olids),
            i.mrid,
            can_delete,
        )


def setup():
    pass