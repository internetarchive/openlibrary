from infogami.utils import delegate
from infogami.utils.view import render_template, public
from openlibrary.utils import uniq
import web
import json


class tags_partials(delegate.page):
    path = "/tags/partials"
    encoding = "json"

    def GET(self):
        # `work_ids` is a comma-separated list of work OLIDs
        i = web.input(work_ids='')

        works = i.work_ids

        tagging_menu = render_template('subjects/tagging_menu', works)

        partials = {
            'tagging_menu': str(tagging_menu),
        }

        return delegate.RawText(json.dumps(partials))


class bulk_tag_works(delegate.page):
    path = "/tags/bulk_tag_works"

    def POST(self):
        i = web.input(work_ids='', tag_subjects='{}')
        works = i.work_ids.split(',')
        incoming_subjects = json.loads(i.tag_subjects)
        docs_to_update = []

        for work in works:
            w = web.ctx.site.get(f"/works/{work}")
            current_subjects = {
                'subjects': uniq(w.get('subjects', '')),
                'subject_people': uniq(w.get('subject_people', '')),
                'subject_places': uniq(w.get('subject_places', '')),
                'subject_times': uniq(w.get('subject_times', '')),
            }
            for subject_type, subject_list in incoming_subjects.items():
                if subject_list:
                    current_subjects[subject_type] = uniq(  # dedupe incoming subjects
                        current_subjects[subject_type] + subject_list
                    )
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
