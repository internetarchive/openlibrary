"""Librarian Edits
"""

import re
import json
import web

from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue
from infogami.utils import delegate
from infogami.utils.view import render_template


class community_edits_queue(delegate.page):
    path = '/merges'

    def POST(self):
        i = web.input(
            work_ids="",
            rtype="merge-works",
            mrid=None,
            action=None,  # approve, close, comment
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
            # normalization
            work_ids = [
                w for w in
                re.split("[ ,]", i.work_ids.replace("/works/", ""))
                if w
            ]
            result = CommunityEditsQueue.submit_work_merge_request(
                work_ids,
                submitter=username,
                comment=i.comment
            )
            return delegate.RawText(json.dumps(result), content_type="application/json")

    def GET(self):
        i = web.input(page=1)
        merge_requests = CommunityEditsQueue.get_requests(page=i.page)
        return render_template('merge_queue', merge_requests=merge_requests)


def setup():
    pass
