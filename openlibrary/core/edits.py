import datetime
import json
from typing import Optional

from infogami.utils.view import public

from openlibrary.i18n import gettext as _

from . import db


@public
def get_status_for_view(status_code: int) -> str:
    """Returns localized status string that corresponds with the given status code."""
    if status_code == CommunityEditsQueue.STATUS['DECLINED']:
        return _('Declined')
    if status_code == CommunityEditsQueue.STATUS['PENDING']:
        return _('Pending')
    if status_code == CommunityEditsQueue.STATUS['MERGED']:
        return _('Merged')
    return _('Unknown')


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
        'closed': [STATUS['DECLINED'], STATUS['MERGED']],
    }

    @classmethod
    def get_requests(
        cls,
        limit: int = 50,
        page: int = 1,
        mode: str = 'all',
        order: str = None,
        **kwargs,
    ):
        oldb = db.get_db()
        wheres = []
        if kwargs.get("status"):
            wheres.append("status=$status")
        if kwargs.get('reviewer') is not None:
            wheres.append(
                # if reviewer="" then get all unassigned MRs
                "reviewer IS NULL" if not kwargs.get('reviewer')
                else "reviewer=$reviewer"
            )
        if "submitter" in kwargs:
            wheres.append(
                # If submitter not specified, default to any
                "submitter IS NOT NULL" if kwargs.get("submitter") is None
                else "submitter=$submitter"
            )
        if "url" in kwargs:
            wheres.append("url=$url")
        if "id" in kwargs:
            wheres.append("id=$id")
        if "status" in kwargs:
            wheres.append("status=$status")

        statuses = cls.MODES[mode]

        data = {}
        if mode != 'all':  # No need to add every status to the WHERE clause
            data = {f'status_{i}': status for i, status in enumerate(statuses)}

        status_wheres = [f'status=${status}' for status in data]
        query_kwargs = {
            "limit": limit,
            "offset": limit * (page - 1),
            "vars": {**kwargs, **data},
        }

        if wheres:
            query_kwargs['where'] = f'{" AND ".join(wheres)}'
        if status_wheres:
            status_query = f'({" OR ".join(status_wheres)})'
            if wheres:
                query_kwargs['where'] = status_query
            else:
                query_kwargs['where'] = f'{query_kwargs["where"]} AND {status_query}'
        if order:
            query_kwargs['order'] = order
        return oldb.select("community_edits_queue", **query_kwargs)

    @classmethod
    def submit_work_merge_request(
        cls, work_ids: list[str], submitter: str, comment: str = None
    ):
        """
        Creates new work merge requests with the given work olids.

        Precondition: OLIDs in work_ids list must be sanitized and normalized.
        """

        url = f"/works/merge?records={','.join(work_ids)}"
        if not cls.exists(url):
            return cls.submit_request(url, submitter=submitter, comment=comment)

    @classmethod
    def submit_author_merge_request(cls, author_ids, submitter, comment=None):
        if not comment:
            # some default note from submitter
            pass
        # XXX IDs should be santiized & normalized
        url = f"/authors/merge?key={'&key='.join(author_ids)}"
        cls.submit_request(url, submitter=submitter, comment=comment)

    @classmethod
    def submit_delete_request(cls, olid, submitter, comment=None):
        if not comment:
            # some default note from submitter
            pass
        url = f"{olid}/-/edit?m=delete"
        cls.submit_request(cls, url, submitter=submitter, comment=comment)

    @classmethod
    def submit_request(
        cls,
        url: str,
        submitter: str,
        reviewer: str = None,
        status: int = STATUS['PENDING'],
        comment: str = None,
    ):
        """
        Inserts a new record into the table.

        Preconditions: All data validations should be completed before calling this method.
        """
        oldb = db.get_db()

        comments = [cls.create_comment(submitter, comment)] if comment else []
        json_comment = json.dumps({"comments": comments})

        return oldb.insert(
            "community_edits_queue",
            submitter=submitter,
            reviewer=reviewer,
            url=url,
            status=status,
            comments=json_comment,
        )

    @classmethod
    def assign_request(
        cls, rid: int, reviewer: Optional[str]
    ) -> dict[str, Optional[str]]:
        """Changes assignees to the request with the given ID.

        This method only modifies requests that are not closed.

        If the given reviewer is the same as the request's reviewer, nothing is
        modified
        """
        request = cls.find_by_id(rid)

        if request['status'] not in cls.MODES['closed']:
            if request['reviewer'] == reviewer:
                return {
                    'status': 'error',
                    'error': f'{reviewer} is already assigned to this request',
                }
            oldb = db.get_db()

            oldb.update(
                "community_edits_queue",
                where="id=$rid",
                reviewer=reviewer,
                status=cls.STATUS['PENDING'],
                updated=datetime.datetime.utcnow(),
                vars={"rid": rid},
            )
            return {
                'reviewer': reviewer,
                'newStatus': get_status_for_view(cls.STATUS['PENDING']),
            }
        return {'status': 'error', 'error': 'This request has already been closed'}

    @classmethod
    def unassign_request(cls, rid: int):
        """
        Changes status of given request to "Pending", and sets reviewer to None.
        """
        oldb = db.get_db()
        oldb.update(
            "community_edits_queue",
            where="id=$rid",
            status=cls.STATUS['PENDING'],
            reviewer=None,
            updated=datetime.datetime.utcnow(),
            vars={"rid": rid},
        )

    @classmethod
    def update_request_status(
        cls, rid: int, status: int, reviewer: str, comment: str = None
    ) -> int:
        """
        Changes the status of the request with the given rid.

        If a comment is included, existing comments list for this request are fetched and
        the new comment is appended.
        """
        oldb = db.get_db()

        update_kwargs = {}

        # XXX Trim whitespace from comment first
        if comment:
            comments = cls.get_comments(rid)
            comments['comments'].append(cls.create_comment(reviewer, comment))
            update_kwargs['comments'] = json.dumps(comments)

        return oldb.update(
            "community_edits_queue",
            where="id=$rid",
            status=status,
            reviewer=reviewer,
            updated=datetime.datetime.utcnow(),
            vars={"rid": rid},
            **update_kwargs,
        )

    @classmethod
    def comment_request(cls, rid: int, username: str, comment: str) -> int:
        oldb = db.get_db()

        comments = cls.get_comments(rid)
        comments['comments'].append(cls.create_comment(username, comment))

        return oldb.update(
            "community_edits_queue",
            where="id=$rid",
            comments=json.dumps(comments),
            updated=datetime.datetime.utcnow(),
            vars={"rid": rid},
        )

    @classmethod
    def find_by_id(cls, rid: int):
        """Returns the record with the given ID."""
        return cls.get_requests(id=rid)[0] or None

    @classmethod
    def exists(cls, url: str) -> bool:
        """Returns True if a request with the given URL exists in the table."""
        return len(cls.get_requests(limit=1, url=url)) > 0

    @classmethod
    def get_comments(cls, rid: int):
        """Fetches the comments for the given request, or an empty comments object."""
        return cls.get_requests(id=rid)[0]['comments'] or {'comments': []}

    @classmethod
    def create_comment(cls, username: str, message: str) -> dict[str, str]:
        """Creates and returns a new comment with the given name and message.
        Timestamp set as current time.
        """
        return {
            # isoformat to avoid to-json issues
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "username": username,
            "message": message,
            # XXX It may be easier to update these comments if they had IDs
        }
