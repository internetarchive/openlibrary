"""Library to generate keys for new documents using database sequences.

Currently new keys are generated for author, edition and work types.
"""

__all__ = [
    "get_new_key",
    "get_new_keys"
]

def get_new_key(site, type):
    """Returns a new key for the given type of document.
    """
    return site.new_key(type)
    
def get_new_keys(site, type, n):
    """Returns n new keys for given type of documents.
    
    Example:
    
        >>> get_new_keys("/type/edition", 2)
        ["/books/OL12M", "/books/OL13M"]
    """
    return [get_new_key(site, type) for i in range(n)]
    