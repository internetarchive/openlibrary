"""Utility functions for processing lists."""

import re

RE_SUBJECT = re.compile("[, _]+")


def get_seeds(work):
    """Returns all seeds of given work."""

    def get_authors(work):
        return [a["author"] for a in work.get("authors", []) if "author" in a]

    def _get_subject(subject, prefix):
        if isinstance(subject, str):
            key = prefix + RE_SUBJECT.sub("_", subject.lower()).strip("_")
            return {"key": key, "name": subject}

    def get_subjects(work):
        subjects = [_get_subject(s, "subject:") for s in work.get("subjects", [])]
        places = [_get_subject(s, "place:") for s in work.get("subject_places", [])]
        people = [_get_subject(s, "person:") for s in work.get("subject_people", [])]
        times = [_get_subject(s, "time:") for s in work.get("subject_times", [])]
        d = {s["key"]: s for s in subjects + places + people + times if s is not None}
        return d.values()

    def get(work):
        yield work["key"]
        for a in get_authors(work):
            yield a["key"]

        for e in work.get("editions", []):
            yield e["key"]

        for s in get_subjects(work):
            yield s["key"]

    return list(get(work))
