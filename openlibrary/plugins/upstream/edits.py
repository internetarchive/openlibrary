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
        i = web.input(
            work_ids="",  # Comma-separated OLIDs (OL1W,OL2W,OL3W,...,OL111W)
            rtype="merge-works",
            mrid=None,
            action=None,  # create, approve, close, comment
            comment=None
        )
        user = accounts.get_current_user()
        username = user['key'].split('/')[-1]
        if i.mrid:
            action = f"{i.action}_request"
            result = getattr(CommunityEditsQueue, action)(
                i.mrid, comment=i.comment
            )
        if i.rtype == "merge-works":
            if i.action == 'create':
                result = self.create_merge_works_request(i.work_ids, username, i.comment)
                return delegate.RawText(json.dumps(result), content_type="application/json")

    def GET(self):
        i = web.input(page=1)
        merge_requests = CommunityEditsQueue.get_requests(page=i.page)
        return render_template('merge_queue', merge_requests=merge_requests)

    def create_merge_works_request(self, work_ids, submitter, comment=None):
        result = create_request(work_ids, submitter, comment)
        return {
            'status': 'ok'
        } if result else {
            'error': 'A request to merge these works has already been submitted.'
        }

def setup():
    pass
