"""Library to mock memcache functionality.
"""

class Client:
    """Mock memcache client."""
    def __init__(self, servers):
        self.servers = servers
        self.cache = {}
        
    def set(self, key, value):
        self.cache[key] = value
        
    def get(self, key):
        return self.cache.get(key)
        
    def add(self, key, value):
        if key not in self.cache:
            self.cache[key] = value
            return True
        else:
            return False