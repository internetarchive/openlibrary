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
                CommunityEditsQueue.decline_request(i.mrid, username, i.comment)
                return delegate.RawText(json.dumps(response()), content_type="application/json")
            if i.action == 'approve':
                CommunityEditsQueue.approve_request(i.mrid, username, i.comment)
                return delegate.RawText(json.dumps(response()), content_type="application/json")
            if i.action == 'comment':
                if i.comment:
                    CommunityEditsQueue.comment_request(i.mrid, username, i.comment)
                    return delegate.RawText(json.dumps(response()), content_type="application/json")
                else:
                    return delegate.RawText(json.dumps(response(status='error', error='No comment sent in request.')))

        elif i.rtype == "merge-works":
            if i.action == 'create':
                result = create_request(i.work_ids, username, i.comment)
                resp = response(id=result) if result else response(status='error', error='A request to merge these works has already been submitted.')
                return delegate.RawText(json.dumps(resp), content_type="application/json")

    def GET(self):
        i = web.input(page=1, open='true', closed='false', submitter=None)

        show_opened = i.open == 'true'
        show_closed = i.closed == 'true'

        mode = 'all' if show_opened and show_closed else (
            'open' if show_opened and not show_closed else 'closed'
        )

        merge_requests = CommunityEditsQueue.get_requests(page=i.page, mode=mode, submitter=i.submitter).list()
        enriched_requests = self.enrich(merge_requests)

        return render_template('merge_queue', merge_requests=enriched_requests, submitter=i.submitter)

    def enrich(self, merge_requests):
        results = []
        for r in merge_requests:
            obj = {
                'id': r['id'],
                'submitter': r['submitter'],
                'reviewer': r['reviewer'],
                'url': r['url'],
                'status': r['status'],  # convert to string?
                'comments': r['comments'],
                'created': r['created'],
                'updated': r['updated'],
            }
            olids = self.extract_olids(r['url'])
            obj['title'] = ''
            for olid in olids:
                book = web.ctx.site.get(f'/works/{olid}')
                if book:
                    if not obj['title']:
                        obj['title'] = book.title
                        break

            results.append(obj)
        return results

    def extract_olids(self, url):
        query_string = url.split('?')[1]
        split_params = query_string.split('&')
        params = {}
        for p in split_params:
            kv = p.split('=')
            params[kv[0]] = kv[1]
        return params['records'].split(',')

def setup():
    pass
