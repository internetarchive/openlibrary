"""Librarian Edits"""

import json

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue, get_status_for_view


def response(status='ok', **kwargs):
    return {'status': status, **kwargs}


def process_merge_request(rtype, data):
    user = accounts.get_current_user()
    username = user['key'].split('/')[-1]
    # Request types can be: create-request, update-request
    if rtype == 'create-request':
        resp = community_edits_queue.create_request(username, **data)
    elif rtype == 'update-request':
        resp = community_edits_queue.update_request(username, **data)
    else:
        resp = response(status='error', error='Unknown request type')
    return resp


class community_edits_queue(delegate.page):
    path = '/merges'

    def GET(self):
        i = web.input(
            page=1,
            limit=25,
            mode="open",
            submitter=None,
            reviewer=None,
            order='desc',
            status=None,
        )
        merge_requests = CommunityEditsQueue.get_requests(
            page=int(i.page),
            limit=int(i.limit),
            mode=i.mode,
            submitter=i.submitter,
            reviewer=i.reviewer,
            order=f'updated {i.order}',
            status=i.status,
        ).list()

        total_found = {
            "open": CommunityEditsQueue.get_counts_by_mode(
                mode='open', submitter=i.submitter, reviewer=i.reviewer
            ),
            "closed": CommunityEditsQueue.get_counts_by_mode(
                mode='closed', submitter=i.submitter, reviewer=i.reviewer
            ),
            "submitters": CommunityEditsQueue.get_submitters(),
            "reviewers": CommunityEditsQueue.get_reviewers(),
        }

        librarians = {
            'submitters': CommunityEditsQueue.get_submitters(),
            'reviewers': CommunityEditsQueue.get_reviewers(),
        }

        return render_template(
            'merge_request_table/merge_request_table',
            total_found,
            librarians,
            merge_requests=merge_requests,
        )

    def POST(self):
        data = json.loads(web.data())
        resp = process_merge_request(data.pop('rtype', ''), data)

        return delegate.RawText(json.dumps(resp), content_type='application/json')

    @staticmethod
    def create_request(
        username,
        action='',
        mr_type=None,
        olids='',
        comment: str | None = None,
        primary: str | None = None,
    ):
        def is_valid_action(action):
            return action in ('create-pending', 'create-merged')

        def needs_unique_url(mr_type):
            return mr_type in (
                CommunityEditsQueue.TYPE['WORK_MERGE'],
                CommunityEditsQueue.TYPE['AUTHOR_MERGE'],
            )

        if is_valid_action(action):
            olid_list = olids.split(',')

            title = community_edits_queue.create_title(mr_type, olid_list)
            url = community_edits_queue.create_url(mr_type, olid_list, primary=primary)

            # Validate URL
            is_valid_url = True
            if needs_unique_url(mr_type) and CommunityEditsQueue.exists(url):
                is_valid_url = False

            if is_valid_url:
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
                    error='A merge request for these items already exists.',
                )
        else:
            resp = response(
                status='error',
                error=f'Action "{action}" is invalid for this request type.',
            )

        return resp

    @staticmethod
    def update_request(username, action='', mrid=None, comment=None):
        # Comment on existing request:
        if action == 'comment':
            if comment:
                CommunityEditsQueue.comment_request(mrid, username, comment)
                resp = response()
            else:
                resp = response(status='error', error='No comment sent in request.')
        # Assign to existing request:
        elif action == 'claim':
            result = CommunityEditsQueue.assign_request(mrid, username)
            resp = response(**result)
        # Unassign from existing request:
        elif action == 'unassign':
            CommunityEditsQueue.unassign_request(mrid)
            status = get_status_for_view(CommunityEditsQueue.STATUS['PENDING'])
            resp = response(newStatus=status)
        # Close request by approving:
        elif action == 'approve':
            CommunityEditsQueue.update_request_status(
                mrid, CommunityEditsQueue.STATUS['MERGED'], username, comment=comment
            )
            resp = response()
        # Close request by declining:
        elif action == 'decline':
            CommunityEditsQueue.update_request_status(
                mrid, CommunityEditsQueue.STATUS['DECLINED'], username, comment=comment
            )
            resp = response()
        # Unknown request:
        else:
            resp = response(
                status='error',
                error=f'Action "{action}" is invalid for this request type.',
            )

        return resp

    @staticmethod
    def create_url(mr_type: int, olids: list[str], primary: str | None = None) -> str:
        if mr_type == CommunityEditsQueue.TYPE['WORK_MERGE']:
            primary_param = f'&primary={primary}' if primary else ''
            return f'/works/merge?records={",".join(olids)}{primary_param}'
        elif mr_type == CommunityEditsQueue.TYPE['AUTHOR_MERGE']:
            return f'/authors/merge?records={",".join(olids)}'
        return ''

    @staticmethod
    def create_title(mr_type: int, olids: list[str]) -> str:
        if mr_type == CommunityEditsQueue.TYPE['WORK_MERGE']:
            for olid in olids:
                book = web.ctx.site.get(f'/works/{olid}')
                if book and book.title:
                    return book.title
        elif mr_type == CommunityEditsQueue.TYPE['AUTHOR_MERGE']:
            for olid in olids:
                author = web.ctx.site.get(f'/authors/{olid}')
                if author and author.name:
                    return author.name
        return 'Unknown record'


def setup():
    pass
