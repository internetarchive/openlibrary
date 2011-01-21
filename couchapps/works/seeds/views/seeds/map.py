import re
def map(doc, re_subject=re.compile("[, _]+")):
    def get_subject_key(prefix, subject):
        if isinstance(subject, basestring):
            key = prefix + re_subject.sub("_", subject.lower()).strip("_")
            return key

    type = doc.get('type', {}).get('key')
    if type == "/type/work":
        work = doc
        editions = work.get('editions', [])
        ebooks = sum(1 for e in editions if 'ocaid' in e)
    
        dates = [d['last_modified']['value'] 
                    for d in [work] + editions
                    if 'last_modified' in d]
        last_modified = max(dates or [""])
        
        subjects = {
            "subjects": work.get("subjects"),
            "people": work.get("subject_people"),
            "places": work.get("subject_places"),
            "times": work.get("subject_times")
        }
        # strip off empty values
        subjects = dict((k, v) for k, v in subjects.items() if v)
        
        counts = [1, len(editions), ebooks, last_modified, subjects]

        # work
        yield doc['key'], counts

        # editions
        for e in doc.get("editions", []):
            yield e['key'], [1, 1, int('ocaid' in e), e.get("last_modified", {}).get('value', ''), subjects]

        # authors
        for a in doc.get('authors', []):
            if 'author' in a:
                yield a['author']['key'], counts

        prefixes = {
            "subjects": "subject:",
            "people": "person:",
            "places": "place:",
            "times": "time:"
        }
        for name, values in subjects.items():
            prefix = prefixes[name]
            for s in values:
                key = get_subject_key(prefix, s)
                if key:
                    yield key, counts[:-1] + [{name: [s]}] 
del re
