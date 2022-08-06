"""Librarian Edits
"""

import json
import web

from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue, get_status_for_view
from infogami.utils import delegate
from infogami.utils.view import render_template


def create_request(olids: str, username: str, comment: str = None):
    work_ids = olids.split(',')
    return CommunityEditsQueue.submit_work_merge_request(
        work_ids,
        submitter=username,
        comment=comment,
    )


def response(status='ok', **kwargs):
    return {'status': status, **kwargs}


class community_edits_queue(delegate.page):
    path = '/merges'

    def POST(self):
        data = json.loads(web.data())
        type = data.get('rtype', '')
        if type:
            del data['rtype']

        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]

        if type == 'merge-works':
            resp = self.work_merge_request(username, **data)
        else:
            resp = response(status='error', error='Unknown request type')

        return delegate.RawText(json.dumps(resp), content_type='application/json')

    def GET(self):
        i = web.input(
            page=1, limit=25, mode="open", submitter=None, reviewer=None, order='desc'
        )
        merge_requests = CommunityEditsQueue.get_requests(
            page=int(i.page),
            limit=int(i.limit),
            mode=i.mode,
            submitter=i.submitter,
            reviewer=i.reviewer,
            order=f'created {i.order}',
        ).list()

        total_found = {
            "open": CommunityEditsQueue.get_counts_by_mode(
                mode='open', submitter=i.submitter, reviewer=i.reviewer
            ),
            "closed": CommunityEditsQueue.get_counts_by_mode(
                mode='closed', submitter=i.submitter, reviewer=i.reviewer
            ),
        }
        return render_template(
            'merge_queue/merge_queue',
            total_found,
            merge_requests=merge_requests,
        )

    def work_merge_request(
        self, username, olids='', mrid=None, action=None, comment=None
    ):
        # Create a new, open work MR
        if action == 'create':
            result = create_request(olids, username, comment)
            if result:
                resp = response(id=result)
            else:
                resp = response(
                    status='error',
                    error='A request to merge these works has already been submitted.',
                )
        # Create a "merged" MR with the same submitter and reviewer (for super-librarian merges)
        elif action == 'create-merged':
            result = CommunityEditsQueue.submit_work_merge_request(
                olids.split(','),
                submitter=username,
                reviewer=username,
                status=CommunityEditsQueue.STATUS['MERGED'],
            )
            resp = response(id=result)
        # Add a comment to an existing MR
        elif action == 'comment':
            if comment:
                CommunityEditsQueue.comment_request(mrid, username, comment)
                resp = response()
            else:
                resp = response(status='error', error='No comment sent in request')
        # Assign an existing MR to a patron
        elif action == 'claim':
            result = CommunityEditsQueue.assign_request(mrid, username)
            resp = response(**result)
        # Unassign an existing MR
        elif action == 'unassign':
            CommunityEditsQueue.unassign_request(mrid)
            status = get_status_for_view(CommunityEditsQueue.STATUS['PENDING'])
            resp = response(newStatus=status)
        # Close a MR by declining the merge
        elif action == "decline":
            status = CommunityEditsQueue.STATUS['DECLINED']
            CommunityEditsQueue.update_request_status(
                mrid, status, username, comment=comment
            )
            resp = response()
        # Close a MR by merging the items
        elif action == 'approve':
            status = CommunityEditsQueue.STATUS['MERGED']
            CommunityEditsQueue.update_request_status(
                mrid, status, username, comment=comment
            )
            resp = response()
        # Idle conversation with the server
        else:
            resp = response(status='error', error='Unknown action')

        return resp

    def extract_olids(self, url):
        query_string = url.split('?')[1]
        split_params = query_string.split('&')
        params = {}
        for p in split_params:
            kv = p.split('=')
            params[kv[0]] = kv[1]
        return params['records'].split(',')


class ui_partials(delegate.page):
    path = '/merges/partials'

    def GET(self):
        i = web.input(type=None, comment='')
        if i.type == 'comment':
            component = render_template('merge_queue/comment', comment_str=i.comment)
            return delegate.RawText(component)


def setup():
    pass
