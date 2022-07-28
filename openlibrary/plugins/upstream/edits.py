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


class community_edits_queue(delegate.page):
    path = '/merges'

    def POST(self):
        def response(status='ok', **kwargs):
            return {'status': status, **kwargs}

        i = web.input(
            work_ids="",  # Comma-separated OLIDs (OL1W,OL2W,OL3W,...,OL111W)
            rtype="merge-works",
            mrid=None,
            action=None,  # create, approve, decline, comment, unassign, create-merged
            comment=None,
        )
        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]
        if i.mrid:  # We are updating an existing merge request
            if i.action == 'comment':
                if i.comment:
                    CommunityEditsQueue.comment_request(i.mrid, username, i.comment)
                    return delegate.RawText(
                        json.dumps(response()), content_type="application/json"
                    )
                else:
                    return delegate.RawText(
                        json.dumps(
                            response(
                                status='error', error='No comment sent in request.'
                            )
                        )
                    )
            elif i.action == 'claim':
                result = CommunityEditsQueue.assign_request(i.mrid, username)
                return delegate.RawText(
                    json.dumps(response(**result)), content_type="application/json"
                )
            elif i.action == 'unassign':
                CommunityEditsQueue.unassign_request(i.mrid)
                status = get_status_for_view(CommunityEditsQueue.STATUS['PENDING'])
                return delegate.RawText(json.dumps(response(newStatus=status)))
            else:
                if i.action == "decline":
                    status = CommunityEditsQueue.STATUS['DECLINED']
                elif i.action == 'approve':
                    status = CommunityEditsQueue.STATUS['MERGED']
                CommunityEditsQueue.update_request_status(
                    i.mrid, status, username, comment=i.comment
                )
                return delegate.RawText(
                    json.dumps(response()), content_type="application/json"
                )
        elif i.rtype == "merge-works":
            if i.action == 'create':
                result = create_request(i.work_ids, username, i.comment)
                resp = (
                    response(id=result)
                    if result
                    else response(
                        status='error',
                        error='A request to merge these works has already been submitted.',
                    )
                )
                return delegate.RawText(
                    json.dumps(resp), content_type="application/json"
                )
            elif i.action == 'create-merged':
                result = CommunityEditsQueue.submit_work_merge_request(
                    i.work_ids.split(','),
                    submitter=username,
                    reviewer=username,
                    status=CommunityEditsQueue.STATUS['MERGED'],
                )
                return delegate.RawText(
                    json.dumps(response(id=result)), content_type='application/json'
                )

    def GET(self):
        i = web.input(page=1, limit=25, mode="open", submitter=None, reviewer=None)
        merge_requests = CommunityEditsQueue.get_requests(
            page=int(i.page),
            limit=int(i.limit),
            mode=i.mode,
            submitter=i.submitter,
            reviewer=i.reviewer,
            order='created desc',
        ).list()

        total_found = CommunityEditsQueue.get_counts_by_mode(
            mode=i.mode, submitter=i.submitter, reviewer=i.reviewer
        )
        return render_template(
            'merge_queue/merge_queue',
            total_found,
            merge_requests=merge_requests,
        )

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
