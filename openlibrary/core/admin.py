"""Admin functionality.
"""

class Stats:
    def __init__(self):
        pass
        
    def get_stats(self, ndays):
        """Returns the stats for last n days as an array."""
        return [i for i in range(ndays)]
        
    def get_summary(self, ndays):
        """Returns the summary of counts for past n days.
        
        Summary can be either sum or average depending on the type of stats.
        This is used to find counts for last 7 days and last 28 days.
        """
        return sum(self.get_counts(ndays))
        
    def get_total(self):
        """Returns the total counts."""
        return 0
            
def get_stats():
    """Returns the stats 
    """
    return {
        "authors": Stats(),
        "editions": Stats(),
        "lists": Stats(),
        "works": Stats(),
        
        "users": Stats(),
        "edits": Stats(),
        
        "unique-ips": Stats(),
        "ebooks-borrowed": Stats(),
    }