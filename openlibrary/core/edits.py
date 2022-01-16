import datetime
from . import db


class CommunityEditsQueue:

    """Schema
    id: Primary identifier
    submitter: username of person that made the request
    reviewer: The username of the person who reviewed the request
    url: URL of the merge request
    status: Either "Pending", "Merged", or "Rejected"
    comment: Short note from reviewer (json blobs (can store timestamps, etc))
    created: created timestamp
    updated: update timestamp
    """

    @classmethod
    def get_requests(cls, limit: int = 50, page: int = 1, **kwargs):
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
        query_kwargs = {
            "limit": limit,
            "offset": limit * (page - 1),
            "vars": kwargs
        }
        if wheres:
            query_kwargs['where'] = " AND ".join(wheres)
        return oldb.select("community_edits_queue", **query_kwargs)

    @classmethod
    def submit_work_merge_request(cls, work_ids, submitter, comment=None):
        if not comment:
            # some default note from submitter
            pass
        # XXX IDs should be santiized & normalized
        # e.g. /works/OL123W -> OL123W
        url = f"/works/merge?records={','.join(work_ids)}"
        cls.submit_request(url, submitter=submitter, comment=comment)

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
    def submit_request(cls, url, submitter, reviewer=None, status=1, comment=None):
        oldb = db.get_db()

        # XXX should there be any validation of the url?
        # i.e. does this represent a valid merge/delete request?
        
        return oldb.insert(
            "community_edits_queue",
            submitter=submitter,
            reviewer=reviewer,
            url=url,
            status=status,
            # XXX comments? TODO
        )

    @classmethod
    def assign_request(cls, rid, reviewer):
        oldb = db.get_db()
        oldb.update(
            "community_edits_queue",
            where="rid=$rid",
            reviewer=reviewer,
            vars={"rid": rid}
        )
    
    @classmethod
    def close_request(cls, rid, comment=None):
        oldb = db.get_db()
        oldb.update(
            "community_edits_queue",
            where="rid=$rid",
            status=0,
            vars={"rid": rid}
        )

    @classmethod
    def approve_request(cls, rid, comment=None):
        oldb = db.get_db()
        oldb.update(
            "community_edits_queue",
            where="rid=$rid",
            status=2,
            vars={"rid": rid}
        )

    @classmethod
    def comment_request(cls, rid, username, comment):
        oldb = db.get_db()
        comments.setdefault("comments", [])
        # isoformat to avoid to-json issues
        comments["comments"].append({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "username": username,
            "message": comment
        })
        return oldb.update(
            "community_edits_queue",
            where="rid=$rid",
            vars={"rid": rid, "comments": comment}
        )
        
