from infogami.utils import delegate

from openlibrary.core import stats
from openlibrary.utils import uniq
import web
import json


class bulk_tag_works(delegate.page):
    path = "/tags/bulk_tag_works"

    def POST(self):
        i = web.input(work_ids='', tags_to_add='', tags_to_remove='', dry_run=False)
        
        if i.dry_run:
          original_works = []
          updated_works = []


        works = i.work_ids.split(',')
        tags_to_add = json.loads(i.tags_to_add or '{}')
        tags_to_remove = json.loads(i.tags_to_remove or '{}')
         
        docs_to_update = []
        docs_adding = 0
        docs_removing = 0 
        
        for work in works:
            original_work = web.ctx.site.get(f"/works/{work}")
            original_works.append(original_work)

            w = original_work

            current_subjects = {
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
            
            updated_works.append(w)

            if i.dry_run:
              return self.show_diff(original_works, updated_works)

            if not i.dry_run:
                docs_to_update.append(
                    w.dict()
                )
            if not i.dry_run:
                web.ctx.site.save_many(docs_to_update, comment="Bulk tagging works")

            # Number of times the handler was hit:
            stats.increment('ol.tags.bulk_update')
            stats.increment('ol.tags.bulk_update.add', n=docs_adding)
            stats.increment('ol.tags.bulk_update.remove', n=docs_removing)

            return delegate.RawText(
                json.dumps({'status': 'success', 'message': 'Tagged works successfully'}), 
                content_type="application/json"        
            )
        
def show_diff(self, original, updated):      
    pass

def setup():
    pass
