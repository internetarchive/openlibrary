from infogami.utils import delegate
from infogami.utils.view import render_template, public
from openlibrary.utils import uniq
import web
import json


class bulk_tag_works(delegate.page):
    path = "/tags/bulk_tag_works"

    def POST(self):
        i = web.input(work_ids='', tags_to_add='', tags_to_remove='')

        works = i.work_ids.split(',')
        tags_to_add = json.loads(i.tags_to_add or '{}')
        tags_to_remove = json.loads(i.tags_to_remove or '{}')

        docs_to_update = []

        for work in works:
            w = web.ctx.site.get(f"/works/{work}")
            current_subjects = {
                'subjects': uniq(w.get('subjects', '')),
                'subject_people': uniq(w.get('subject_people', '')),
                'subject_places': uniq(w.get('subject_places', '')),
                'subject_times': uniq(w.get('subject_times', '')),
            }
            for subject_type, add_list in tags_to_add.items():
                if add_list:
                    current_subjects[subject_type] = uniq(  # dedupe incoming subjects
                        current_subjects[subject_type] + add_list
                    )
                    w[subject_type] = current_subjects[subject_type]

            for subject_type, remove_list in tags_to_remove.items():
                if remove_list:
                    current_subjects[subject_type] = [
                        item for item in current_subjects[subject_type] if item not in remove_list
                    ]
                    w[subject_type] = current_subjects[subject_type]

            docs_to_update.append(
                w.dict()
            )  # need to convert class to raw dict in order for save_many to work

        web.ctx.site.save_many(docs_to_update, comment="Bulk tagging works")

        def response(msg, status="success"):
            return delegate.RawText(
                json.dumps({status: msg}), content_type="application/json"
            )

        return response('Tagged works successfully')


def setup():
    pass
