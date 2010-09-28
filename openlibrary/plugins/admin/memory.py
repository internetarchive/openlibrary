"""memory profiler
"""
import gc
import web
from collections import defaultdict

_mark = {}
_mark_ids = {}

class Storage(web.Storage):
    pass

def mark():
    """Mark the current counts to show the difference."""
    global _mark, _mark_ids
    
    objects= get_objects()
    d = defaultdict(set)
    for obj in objects:
        d[_get_type(obj)].add(id(obj))
        
    _mark_ids = d
    _mark = get_all_counts()
    
def get_counts():
    counts = get_all_counts()
    
    d = [Storage(type=type, count=count, mark=_mark.get(type, 0), diff=count - _mark.get(type, 0))
        for type, count in counts.items()]
    return d

def get_all_counts():
    """Returns the counts of live objects."""
    objects= get_objects()

    d = defaultdict(lambda: 0)
    for obj in objects:
        d[_get_type(obj)] += 1

    return d
    
def get_objects():
    """Returns a list of live objects."""
    objects = gc.get_objects()
    dicts = set(id(o.__dict__) for o in objects if hasattr(o, "__dict__"))    
    return (obj for obj in gc.get_objects() if obj is not _mark and id(obj) not in dicts)
    
def get_objects_by_type(type):
    return (obj for obj in get_objects() if _get_type(obj) == type)

def _get_type(obj):
    """Returns the type of given object as string.
    """
    try:
        t = obj.__class__
    except:
        t = type(obj)

    mod = t.__module__
    name = t.__name__
    if mod != "__builtin__":
        name = mod + "." + name
    return name
