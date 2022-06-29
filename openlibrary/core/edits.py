import datetime
import json

from infogami.utils.view import public

from openlibrary.i18n import gettext as _

from . import db

@public
def get_status_for_view(status_code):
    if status_code == CommunityEditsQueue.STATUS['DECLINED']:
        return _('Declined')
    if status_code == CommunityEditsQueue.STATUS['PENDING']:
        return _('Pending')
    if status_code == CommunityEditsQueue.STATUS['MERGED']:
        return _('Merged')

class CommunityEditsQueue:

    """Schema
    id: Primary identifier
    submitter: username of person that made the request
    reviewer: The username of the person who reviewed the request
    url: URL of the merge request
    status: Either "Pending", "Merged", or "Declined"
    comment: Short note from reviewer (json blobs (can store timestamps, etc))
    created: created timestamp
    updated: update timestamp
    """

    STATUS = {
        'DECLINED': 0,
        'PENDING': 1,
        'MERGED': 2,
    }

    MODES = {
        'all': [STATUS['DECLINED'], STATUS['PENDING'], STATUS['MERGED']],
        'open': [STATUS['PENDING']],
        'closed': [STATUS['DECLINED'], STATUS['MERGED']]
    }

    @classmethod
    def get_requests(cls, limit: int = 50, page: int = 1, mode: str = 'all', order: str = None, **kwargs):
        oldb = db.get_db()
        wheres = []
        if kwargs.get("status"):
            wheres.append("status=$status")
        if "reviewer" in kwargs:
            wheres.append("reviewer='$reviewer'")
        if "submitter" in kwargs:
            if kwargs.get("submitter") is None:
                wheres.append("submitter IS NOT NULL")
            else:
                wheres.append("submitter=$submitter")
        if "url" in kwargs:
            wheres.append("url=$url")
        if "id" in kwargs:
            wheres.append("id=$id")
        if "status" in kwargs:
            wheres.append("status=$status")

        statuses = cls.MODES[mode]

        data = {}
        status_wheres = []

        for i, status in enumerate(statuses):
            data[f'status_{i}'] = status
            status_wheres.append(f'status=$status_{i}')

        query_kwargs = {
            "limit": limit,
            "offset": limit * (page - 1),
            "vars": {**kwargs, **data}
        }

        query_kwargs['where'] = f'({" OR ".join(status_wheres)})'
        if wheres:
            query_kwargs['where'] = f'{" AND ".join(wheres)} AND {query_kwargs["where"]}'
        if order:
            query_kwargs['order'] = order
        return oldb.select("community_edits_queue", **query_kwargs)

    @classmethod
    def submit_work_merge_request(cls, work_ids, submitter, comment=None):
        # XXX IDs should be santiized & normalized
        # e.g. /works/OL123W -> OL123W
        url = f"/works/merge?records={','.join(work_ids)}"
        return cls.submit_request(url, submitter=submitter, comment=comment)

    @classmethod
    def submit_author_merge_request(cls, author_ids, submitter, comment=None):
        if not comment:
            # some default note from submitter
            pass
        # XXX IDs should be santiized & normalized
        url = "/authors/merge?key={'&key='.join(author_ids)}"
        cls.submit_request(url, submitter=submitter, comment=comment)

    @classmethod
    def submit_delete_request(cls, olid, submitter, comment=None):
        if not comment:
            # some default note from submitter
            pass
        url = f"{olid}/-/edit?m=delete"
        cls.submit_request(cls, url, submitter=submitter, comment=comment)

    @classmethod
    def submit_request(cls, url, submitter, reviewer=None, status=STATUS['PENDING'], comment=None):
        comments = [cls.create_comment(submitter, comment)] if comment else []

        oldb = db.get_db()

        json_comment = json.dumps({"comments": comments})
        # XXX should there be any validation of the url?
        # i.e. does this represent a valid merge/delete request?
        if not cls.exists(url):
            return oldb.insert(
                "community_edits_queue",
                submitter=submitter,
                reviewer=reviewer,
                url=url,
                status=status,
                comments=json_comment
            )

    @classmethod
    def assign_request(cls, rid, reviewer):
        oldb = db.get_db()
        oldb.update(
            "community_edits_queue",
            where="id=$rid",
            reviewer=reviewer,
            vars={"rid": rid}
        )

    @classmethod
    def decline_request(cls, rid, reviewer, comment=None):
        if not comment:
            comment = 'Request declined without comment.'
        comments = cls.get_comments(rid)
        comments['comments'].append(cls.create_comment(reviewer, comment))

        oldb = db.get_db()
        oldb.update(
            "community_edits_queue",
            where="id=$rid",
            status=cls.STATUS['DECLINED'],
            reviewer=reviewer,
            comments=json.dumps(comments),
            vars={"rid": rid}
        )

    @classmethod
    def approve_request(cls, rid, reviewer, comment=None):
        if not comment:
            comment = 'Request approved without comment.'
        comments = cls.get_comments(rid)
        comments['comments'].append(cls.create_comment(reviewer, comment))

        oldb = db.get_db()
        oldb.update(
            "community_edits_queue",
            where="id=$rid",
            status=cls.STATUS['MERGED'],
            reviewer=reviewer,
            comments=json.dumps(comments),
            vars={"rid": rid}
        )

    @classmethod
    def comment_request(cls, rid, username, comment):
        comments = cls.get_comments(rid)
        comments['comments'].append(cls.create_comment(username, comment))

        oldb = db.get_db()
        return oldb.update(
            "community_edits_queue",
            where="id=$rid",
            comments=json.dumps(comments),
            vars={"rid": rid}
        )

    @classmethod
    def exists(cls, url):
        return len(cls.get_requests(limit=1, url=url)) > 0

    @classmethod
    def get_comments(cls, rid):
        return cls.get_requests(id=rid)[0]['comments'] or {'comments': []}

    @classmethod
    def create_comment(cls, username, message):
        return {
            # isoformat to avoid to-json issues
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "username": username,
            "message": message,
        }
