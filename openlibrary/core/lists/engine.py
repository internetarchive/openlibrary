"""Utility functions for processing lists.
"""

import web
import simplejson

def reduce_seeds(values):
    """Function to reduce the seed values got from works db.
    """
    pass
    
def get_seeds(work):
    """Returns all seeds of given work."""
    pass
    
class SubjectProcessor:
    """Processor to take a dict of subjects, places, people and times and build a list of ranked subjects.
    """
    def __init__(self):
        self.subjects = collections.defaultdict(list)

    def add_subjects(self, subjects):
        for s in subjects.get("subjects", []):
            self._add_subject('subject:', s)

        for s in subjects.get("people", []):
            self._add_subject('person:', s)

        for s in subjects.get("places", []):
            self._add_subject('place:', s)

        for s in subjects.get("times", []):
            self._add_subject('time:', s)

    def _add_subject(self, prefix, name):
        s = self._get_subject(prefix, name)
        if s:
            self.subjects[s['key']].append(s['name'])

    def _get_subject(self, prefix, subject_name):
        if isinstance(subject_name, basestring):
            key = prefix + RE_SUBJECT.sub("_", subject_name.lower()).strip("_")
            return {"key": key, "name": subject_name}

    def _most_used(self, seq):
        d = collections.defaultdict(lambda: 0)
        for x in seq:
            d[x] += 1

        return sorted(d, key=lambda k: d[k], reverse=True)[0]

    def top_subjects(self, limit=100):
        subjects = [{"key": key, "name": self._most_used(names), "count": len(names)} for key, names in self.subjects.items()]
        subjects.sort(key=lambda s: s['count'], reverse=True)
        return subjects[:limit]
