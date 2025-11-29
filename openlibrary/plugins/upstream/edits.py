"""Librarian Edits"""

import json
import logging

import web

from infogami.utils import delegate
from infogami.utils.view import render_template
from openlibrary import accounts
from openlibrary.core.edits import CommunityEditsQueue, get_status_for_view

logger = logging.getLogger("openlibrary.community_edits_queue")


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
        elif mr_type == CommunityEditsQueue.TYPE['DELETION']:
            # Bulk deletion page for works (and possibly other record types later)
            return f'/works/delete?records={",".join(olids)}'
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
        elif mr_type == CommunityEditsQueue.TYPE['DELETION'] and olids:
            # Single deletion type - check all entity types
            olid = olids[0]
            # Try work first
            record = web.ctx.site.get(f'/works/{olid}')
            if not record:
                # Try edition
                record = web.ctx.site.get(f'/books/{olid}')
            if not record:
                # Try author
                record = web.ctx.site.get(f'/authors/{olid}')
            if record:
                return (
                    getattr(record, 'title', None)
                    or getattr(record, 'name', None)
                    or 'Unknown record'
                )
        return 'Unknown record'

    @staticmethod
    def delete_request(
        username,
        action='',
        mr_type=None,
        olids='',
        comment: str | None = None,
    ):
        web.debug("=" * 60)
        web.debug("🗑️ delete_request() called")
        web.debug("=" * 60)

        logger.info("=" * 60)
        logger.info("🗑️ delete_request() called")
        logger.info("=" * 60)

        web.debug("Parameters:")
        web.debug(f"  username: {username}")
        web.debug(f"  action: {action}")
        web.debug(f"  mr_type: {mr_type}")
        web.debug(f"  olids: {olids}")
        web.debug(f"  comment: {comment if comment else '(none)'}")

        logger.info("Parameters:")
        logger.info("  username: %s", username)
        logger.info("  action: %s", action)
        logger.info("  mr_type: %s", mr_type)
        logger.info("  olids: %s", olids)
        logger.info("  comment: %s", comment if comment else "(none)")

        def is_valid_action(action):
            valid = action in ('create-pending', 'create-merged')
            web.debug(f"Action validation: '{action}' -> {valid}")
            logger.debug("Action validation: '%s' -> %s", action, valid)
            return valid

        if is_valid_action(action):
            web.debug("✓ Action is valid, processing...")
            logger.info("✓ Action is valid, processing...")

            olid_list = olids.split(',')
            web.debug(f"Split OLIDs: {olid_list} (count: {len(olid_list)})")
            logger.info("Split OLIDs: %s (count: %d)", olid_list, len(olid_list))

            web.debug("Creating title...")
            logger.info("Creating title...")
            title = community_edits_queue.create_title(mr_type, olid_list)
            web.debug(f"  Title: {title}")
            logger.info("  Title: %s", title)

            web.debug("Creating URL...")
            logger.info("Creating URL...")
            url = community_edits_queue.create_url(mr_type, olid_list)
            web.debug(f"  URL: {url}")
            logger.info("  URL: %s", url)

            if action == 'create-pending':
                web.debug(f"Submitting PENDING request for user: {username}")
                logger.info("Submitting PENDING request for user: %s", username)

                result = CommunityEditsQueue.submit_request(
                    url, username, title=title, comment=comment, mr_type=mr_type
                )

                web.debug(f"  Result ID: {result}")
                logger.info("  Result ID: %s", result)

            elif action == 'create-merged':
                web.debug(f"Submitting MERGED request for user: {username}")
                logger.info("Submitting MERGED request for user: %s", username)

                result = CommunityEditsQueue.submit_request(
                    url,
                    username,
                    title=title,
                    comment=comment,
                    reviewer=username,
                    status=CommunityEditsQueue.STATUS['MERGED'],
                    mr_type=mr_type,
                )

                web.debug(f"  Result ID: {result}")
                logger.info("  Result ID: %s", result)

            if result:
                web.debug(f"✓ Request creation successful with ID: {result}")
                logger.info("✓ Request creation successful with ID: %s", result)
                resp = response(id=result)
            else:
                web.debug("❌ Request creation failed - no result returned")
                logger.error("❌ Request creation failed - no result returned")
                resp = response(status='error', error='Request creation failed.')
        else:
            web.debug(f"❌ Invalid action: '{action}'")
            logger.warning("❌ Invalid action: '%s'", action)
            resp = response(
                status='error',
                error=f'Action "{action}" is invalid for this request type.',
            )

        web.debug(f"Returning response: {resp}")
        web.debug("=" * 60)
        logger.info("Returning response: %s", resp)
        logger.info("=" * 60)

        return resp


class works_delete_page(delegate.page):
    path = '/works/delete'

    def GET(self):
        web.debug("=" * 60)
        web.debug("📥 GET /works/delete - REQUEST START")
        web.debug("=" * 60)

        logger.info("=" * 60)
        logger.info("📥 GET /works/delete - REQUEST START")
        logger.info("=" * 60)

        i = web.input(records='', mrid=None)

        web.debug(f"Raw Input - records: {i.records}, mrid: {i.mrid}")
        logger.info("Raw Input:")
        logger.info("  records: %s", i.records)
        logger.info("  mrid: %s", i.mrid)

        if not i.records:
            web.debug("⚠️ No works provided - returning 404")
            logger.warning("⚠️ No works provided - returning 404")
            raise web.notfound("No works provided")

        olids = [olid for olid in i.records.split(',') if olid]
        web.debug(f"Parsed OLIDs: {olids} (count: {len(olids)})")
        logger.info("Parsed OLIDs: %s (count: %d)", olids, len(olids))

        works = []
        web.debug("Fetching work records from site...")
        logger.info("Fetching work records from site...")
        for olid in olids:
            web.debug(f"  Attempting to fetch: /works/{olid}")
            logger.debug("  Attempting to fetch: /works/%s", olid)
            rec = web.ctx.site.get(f'/works/{olid}')
            if rec:
                works.append(rec)
                web.debug(f"  ✓ Found: {olid} | Title: {rec.get('title', 'Untitled')}")
                logger.info(
                    "  ✓ Found: %s | Title: %s", olid, rec.get('title', 'Untitled')
                )
            else:
                web.debug(f"  ✗ Not found: {olid}")
                logger.warning("  ✗ Not found: %s", olid)

        web.debug(f"Successfully loaded {len(works)}/{len(olids)} works")
        logger.info("Successfully loaded %d/%d works", len(works), len(olids))

        user = accounts.get_current_user()
        web.debug("User Authentication:")
        logger.info("User Authentication:")
        if user:
            web.debug(f"  User Key: {user['key']}")
            web.debug(f"  Username: {user['key'].split('/')[-1]}")
            web.debug(f"  Has web.ctx.user: {hasattr(web.ctx, 'user')}")
            logger.info("  User Key: %s", user['key'])
            logger.info("  Username: %s", user['key'].split('/')[-1])
            logger.info("  Has web.ctx.user: %s", hasattr(web.ctx, "user"))
            if hasattr(web.ctx, "user"):
                web.debug(f"  Is Super Librarian: {web.ctx.user.is_super_librarian()}")
                logger.info(
                    "  Is Super Librarian: %s", web.ctx.user.is_super_librarian()
                )
        else:
            web.debug("  No user logged in")
            logger.info("  No user logged in")

        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True
            web.debug("✓ User has deletion privileges")
            logger.info("✓ User has deletion privileges")
        else:
            web.debug("✗ User does NOT have deletion privileges")
            logger.info("✗ User does NOT have deletion privileges")

        web.debug("Rendering template 'delete_ile/delete_works'")
        web.debug(
            f"Template params: works={len(works)}, olids={','.join(olids)}, mrid={i.mrid}, can_delete={can_delete}"
        )
        logger.info("Rendering template 'delete_ile/delete_works'")
        logger.info(
            "Template params: works=%d, olids=%s, mrid=%s, can_delete=%s",
            len(works),
            ",".join(olids),
            i.mrid,
            can_delete,
        )

        web.debug("=" * 60)
        web.debug("📥 GET /works/delete - REQUEST END")
        web.debug("=" * 60)
        logger.info("=" * 60)
        logger.info("📥 GET /works/delete - REQUEST END")
        logger.info("=" * 60)

        return render_template(
            'delete_ile/delete_works',
            works,
            ",".join(olids),
            i.mrid,
            can_delete,
        )

    def POST(self):
        web.debug("=" * 60)
        web.debug("🗑 POST /works/delete - DELETE REQUEST START")
        web.debug("=" * 60)

        logger.info("=" * 60)
        logger.info("🗑 POST /works/delete - DELETE REQUEST START")
        logger.info("=" * 60)

        i = web.input(records='', comment='', mrid=None)

        web.debug(
            f"Raw POST Input - records: {i.records}, comment: {i.comment}, mrid: {i.mrid}"
        )
        logger.info("Raw POST Input:")
        logger.info("  records: %s", i.records)
        logger.info("  comment: %s", i.comment)
        logger.info("  mrid: %s", i.mrid)

        user = accounts.get_current_user()
        if not user:
            web.debug(
                "⚠️ Unauthenticated user attempted deletion - redirecting to login"
            )
            logger.warning(
                "⚠️ Unauthenticated user attempted deletion - redirecting to login"
            )
            raise web.seeother('/account/login')

        username = user['key'].split('/')[-1]
        web.debug(f"Authenticated User: {username} (key: {user['key']})")
        logger.info("Authenticated User: %s (key: %s)", username, user['key'])

        web.debug("Preparing delete request:")
        web.debug("  action: create-pending")
        web.debug(f"  mr_type: {CommunityEditsQueue.TYPE['DELETION']} (DELETION)")
        web.debug(f"  olids: {i.records}")
        web.debug(f"  comment: {i.comment if i.comment else '(none)'}")

        logger.info("Preparing delete request:")
        logger.info("  action: create-pending")
        logger.info("  mr_type: %s (DELETION)", CommunityEditsQueue.TYPE['DELETION'])
        logger.info("  olids: %s", i.records)
        logger.info("  comment: %s", i.comment if i.comment else "(none)")

        resp = community_edits_queue.delete_request(
            username=username,
            action='create-pending',
            mr_type=CommunityEditsQueue.TYPE['DELETION'],
            olids=i.records,
            comment=i.comment or None,
        )

        web.debug("Delete Request Response:")
        web.debug(f"  Status: {resp.get('status')}")
        if resp.get('id'):
            web.debug(f"  Request ID: {resp.get('id')}")
        if resp.get('error'):
            web.debug(f"  Error: {resp.get('error')}")
        web.debug(f"  Full Response: {json.dumps(resp)}")

        logger.info("Delete Request Response:")
        logger.info("  Status: %s", resp.get('status'))
        if resp.get('id'):
            logger.info("  Request ID: %s", resp.get('id'))
        if resp.get('error'):
            logger.error("  Error: %s", resp.get('error'))
        logger.info("  Full Response: %s", json.dumps(resp))

        if resp.get('status') == 'error':
            web.debug("❌ DELETE REQUEST FAILED")
            web.debug(f"Error Details: {resp.get('error')}")
            logger.error("❌ DELETE REQUEST FAILED")
            logger.error("Error Details: %s", resp.get("error"))
            logger.info("=" * 60)
            return response(status="error", error=resp.get("error"))

        web.debug("✓ Delete request submitted successfully")
        logger.info("✓ Delete request submitted successfully")

        # Re-fetch authors for display
        olids = [olid for olid in i.records.split(',') if olid]
        web.debug(f"Re-fetching {len(olids)} authors for post-submit display")
        logger.info("Re-fetching %d authors for post-submit display", len(olids))

        authors = []
        for olid in olids:
            rec = web.ctx.site.get(f'/authors/{olid}')
            if rec:
                authors.append(rec)
                web.debug(f"  ✓ Re-fetched: {olid}")
                logger.debug("  ✓ Re-fetched: %s", olid)

        web.debug(f"Re-fetched {len(authors)} authors")
        logger.info("Re-fetched %d authors", len(authors))

        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True

        web.debug("Re-rendering delete page:")
        web.debug(f"  Authors: {len(authors)}")
        web.debug(f"  OLIDs: {','.join(olids)}")
        web.debug(f"  MRID: {i.mrid}")
        web.debug(f"  Can Delete: {can_delete}")

        logger.info("Re-rendering delete page:")
        logger.info("  Authors: %d", len(authors))
        logger.info("  OLIDs: %s", ",".join(olids))
        logger.info("  MRID: %s", i.mrid)
        logger.info("  Can Delete: %s", can_delete)

        web.debug("=" * 60)
        web.debug("🗑 POST /authors/delete - DELETE REQUEST END")
        web.debug("=" * 60)

        logger.info("=" * 60)
        logger.info("🗑 POST /authors/delete - DELETE REQUEST END")
        logger.info("=" * 60)

        return render_template(
            'delete_ile/delete_authors',
            authors,
            ",".join(olids),
            i.mrid,
            can_delete,
        )


class authors_delete_page(delegate.page):
    path = '/authors/delete'

    def GET(self):
        i = web.input(records='', mrid=None)

        if not i.records:
            raise web.notfound("No authors provided")

        olids = [olid for olid in i.records.split(',') if olid]

        authors = []
        for olid in olids:
            rec = web.ctx.site.get(f'/authors/{olid}')
            if rec:
                authors.append(rec)

        user = accounts.get_current_user()
        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True

        return render_template(
            'delete_ile/delete_authors',
            authors,
            ",".join(olids),
            i.mrid,
            can_delete,
        )

    def POST(self):
        i = web.input(records='', comment='', mrid=None)

        user = accounts.get_current_user()
        if not user:
            raise web.seeother('/account/login')

        username = user['key'].split('/')[-1]

        resp = community_edits_queue.delete_request(
            username=username,
            action='create-pending',
            mr_type=CommunityEditsQueue.TYPE['DELETION'],
            olids=i.records,
            comment=i.comment or None,
        )

        if resp.get('status') == 'error':
            return response(status="error", error=resp.get("error"))

        olids = [olid for olid in i.records.split(',') if olid]
        authors = [
            web.ctx.site.get(f'/authors/{olid}')
            for olid in olids
            if web.ctx.site.get(f'/authors/{olid}')
        ]

        can_delete = False
        if user and hasattr(web.ctx, "user") and web.ctx.user.is_super_librarian():
            can_delete = True

        return render_template(
            'delete_ile/delete_authors',
            authors,
            ",".join(olids),
            i.mrid,
            can_delete,
        )


def setup():
    pass
