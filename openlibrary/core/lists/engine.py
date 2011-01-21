"""Utility functions for processing lists.
"""

import collections
import re

import simplejson
import web

def reduce_seeds(values):
    """Function to reduce the seed values got from works db.
    """
    d = {
        "works": 0,
        "editions": 0,
        "ebooks": 0,
        "last_update": "",
    }
    subject_processor = SubjectProcessor()
    
    for v in values:
        d["works"] += v[0]
        d['editions'] += v[1]
        d['ebooks'] += v[2]
        d['last_update'] = max(d['last_update'], v[3])
        subject_processor.add_subjects(v[4])
        
    d['subjects'] = subject_processor.top_subjects()
    return d
    
RE_SUBJECT = re.compile("[, _]+")

def get_seeds(work):
    """Returns all seeds of given work."""
    def get_authors(work):
        return [a['author'] for a in work.get('authors', []) if 'author' in a]

    def _get_subject(subject, prefix):
        if isinstance(subject, basestring):
            key = prefix + RE_SUBJECT.sub("_", subject.lower()).strip("_")
            return {"key": key, "name": subject}
            
    def get_subjects(work):
        subjects = [_get_subject(s, "subject:") for s in work.get("subjects", [])]
        places = [_get_subject(s, "place:") for s in work.get("subject_places", [])]
        people = [_get_subject(s, "person:") for s in work.get("subject_people", [])]
        times = [_get_subject(s, "time:") for s in work.get("subject_times", [])]
        d = dict((s['key'], s) for s in subjects + places + people + times if s is not None)
        return d.values()
    
    def get(work):
        yield work['key']
        for a in get_authors(work):
            yield a['key']
        
        for e in work.get('editions', []):
            yield e['key']
        
        for s in get_subjects(work):
            yield s['key']
            
    return list(get(work))
    
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
