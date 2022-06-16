"""Librarian Edits
"""

import json
import web

from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue
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
            action=None,  # create, approve, decline, comment
            comment=None
        )
        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]
        if i.mrid:  # We are updating an existing merge request
            if i.action == "decline":
                result = CommunityEditsQueue.decline_request(i.mrid, username, i.comment)
                return delegate.RawText(json.dumps(response()), content_type="application/json")
            if i.action == 'approve':
                result = CommunityEditsQueue.approve_request(i.mrid, username, i.comment)
                return delegate.RawText(json.dumps(response()), content_type="application/json")

        elif i.rtype == "merge-works":
            if i.action == 'create':
                result = create_request(i.work_ids, username, i.comment)
                resp = response(id=result) if result else response(status='error', error='A request to merge these works has already been submitted.')
                return delegate.RawText(json.dumps(resp), content_type="application/json")

    def GET(self):
        i = web.input(page=1, open='true', closed='false')

        show_opened = i.open == 'true'
        show_closed = i.closed == 'true'

        mode = 'all' if show_opened and show_closed else (
            'open' if show_opened and not show_closed else 'closed'
        )

        merge_requests = CommunityEditsQueue.get_requests(page=i.page, mode=mode)
        return render_template('merge_queue', merge_requests=merge_requests)

def setup():
    pass
