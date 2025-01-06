import json

import web

from infogami.utils import delegate
from openlibrary.core import stats
from openlibrary.utils import uniq


class bulk_tag_works(delegate.page):
    path = "/tags/bulk_tag_works"

    def POST(self):
        i = web.input(work_ids='', tags_to_add='', tags_to_remove='')

        works = i.work_ids.split(',')
        tags_to_add = json.loads(i.tags_to_add or '{}')
        tags_to_remove = json.loads(i.tags_to_remove or '{}')

        docs_to_update = []
        # Number of tags added per work:
        docs_adding = 0
        # Number of tags removed per work:
        docs_removing = 0

        for work in works:
            w = web.ctx.site.get(f"/works/{work}")

            current_subjects = {
                # XXX : Should an empty list be the default for these?
                'subjects': uniq(w.get('subjects', '')),
                'subject_people': uniq(w.get('subject_people', '')),
                'subject_places': uniq(w.get('subject_places', '')),
                'subject_times': uniq(w.get('subject_times', '')),
            }
            for subject_type, add_list in tags_to_add.items():
                if add_list:
                    orig_len = len(current_subjects[subject_type])
                    current_subjects[subject_type] = uniq(  # dedupe incoming subjects
                        current_subjects[subject_type] + add_list
                    )
                    docs_adding += len(current_subjects[subject_type]) - orig_len
                    w[subject_type] = current_subjects[subject_type]

            for subject_type, remove_list in tags_to_remove.items():
                if remove_list:
                    orig_len = len(current_subjects[subject_type])
                    current_subjects[subject_type] = [
                        item
                        for item in current_subjects[subject_type]
                        if item not in remove_list
                    ]
                    docs_removing += orig_len - len(current_subjects[subject_type])
                    w[subject_type] = current_subjects[subject_type]

            docs_to_update.append(
                w.dict()
            )  # need to convert class to raw dict in order for save_many to work

        web.ctx.site.save_many(docs_to_update, comment="Bulk tagging works")

        def response(msg, status="success"):
            return delegate.RawText(
                json.dumps({status: msg}), content_type="application/json"
            )

        # Number of times the handler was hit:
        stats.increment('ol.tags.bulk_update')
        stats.increment('ol.tags.bulk_update.add', n=docs_adding)
        stats.increment('ol.tags.bulk_update.remove', n=docs_removing)

        return response('Tagged works successfully')


def setup():
    pass
