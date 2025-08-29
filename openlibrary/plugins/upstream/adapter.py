"""
Legacy file now containing a few helper methods.
"""

conversions = {
    #    '/people/': '/user/',
    #    '/books/': '/b/',
    #    '/authors/': '/a/',
    #    '/languages/': '/l/',
    '/templates/': '/upstream/templates/',
    '/macros/': '/upstream/macros/',
    '/js/': '/upstream/js/',
    '/css/': '/upstream/css/',
    '/old/templates/': '/templates/',
    '/old/macros/': '/macros/',
    '/old/js/': '/js/',
    '/old/css/': '/css/',
}

# inverse of conversions
iconversions = {v: k for k, v in conversions.items()}


def convert_key(key: str | None, mapping: dict[str, str] | None = None) -> str | None:
    """
    >>> convert_key("/authors/OL1A", {'/authors/': '/a/'})
    '/a/OL1A'
    """
    mapping = mapping or conversions
    if key is None:
        return None
    elif key == '/':
        return '/upstream'

    for new, old in mapping.items():
        if key.startswith(new):
            key2 = old + key[len(new) :]
            return key2
    return key


def convert_dict(d, mapping: dict[str, str] | None = None):
    """
    >>> convert_dict({'author': {'key': '/authors/OL1A'}}, {'/authors/': '/a/'})
    {'author': {'key': '/a/OL1A'}}
    """
    mapping = mapping or conversions
    if isinstance(d, dict):
        if 'key' in d:
            d['key'] = convert_key(d['key'], mapping)
        for k, v in d.items():
            d[k] = convert_dict(v, mapping)
        return d
    elif isinstance(d, list):
        return [convert_dict(x, mapping) for x in d]
    else:
        return d


def unconvert_key(key: str | None) -> str | None:
    if key == '/upstream':
        return '/'
    return convert_key(key, iconversions)


def unconvert_dict(d):
    return convert_dict(d, iconversions)
