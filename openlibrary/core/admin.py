"""Admin functionality.
"""

import datetime

import couchdb

from infogami import config


class Stats:
    def __init__(self, docs = None, key = None, total_key = None):
        if docs == None and key == None and total_key == None:
            self.stats = [0]*30
            self.total = "data unavailable"
            self.latest = self.previous = 0
        else:
            self.stats = [x.get(key, 0) for x in docs]
            self.latest = docs[-1].get(key, 0)
            self.previous = docs[-2].get(key, 0)
            try:
                # Last available total count
                self.total = (x for x in reversed(docs) if total_key in x).next()[total_key]
            except KeyError:
                self.total = ""
                
    def get_counts(self, ndays = 28):
        """Returns the stats for last n days as an array."""
        retval = zip(range(0, ndays*5, 5), self.stats[-ndays:]) # The *5 and 5 are for the bar widths
        return retval
        
    def get_summary(self, ndays = 28):
        """Returns the summary of counts for past n days.
        
        Summary can be either sum or average depending on the type of stats.
        This is used to find counts for last 7 days and last 28 days.
        """
        return sum(x[1] for x in self.get_counts(ndays))
        


            
def get_stats(ndays = 30):
    """Returns the stats for the past `ndays`"""
    try:
        admin_db = couchdb.Database(config.admin.counts_db)
        end      = datetime.datetime.now().strftime("counts-%Y-%m-%d")
        start    = (datetime.datetime.now() - datetime.timedelta(days = ndays)).strftime("counts-%Y-%m-%d")
        docs = [x.doc for x in admin_db.view("_all_docs",
                                             startkey_docid = start,
                                             endkey_docid   = end,
                                             include_docs = True)]
        retval = dict(human_edits = Stats(docs, "human_edits", "human_edits"),
                      bot_edits   = Stats(docs, "bot_edits", "bot_edits"),
                      lists       = Stats(docs, "lists", "total_lists"),
                      visitors    = Stats(docs, "visitors", "visitors"),
                      members     = Stats(docs, "members", "total_members"),
                      works       = Stats(docs, "works", "total_works"),
                      editions    = Stats(docs, "editions", "total_editions"),
                      ebooks      = Stats(docs, "ebooks", "total_ebooks"),
                      covers      = Stats(docs, "covers", "total_covers"),
                      authors     = Stats(docs, "authors", "total_authors"),
                      subjects    = Stats(docs, "subjects", "total_subjects"))
    except Exception:
        retval = dict(edits = Stats(),
                      lists = Stats(),
                      visitors = Stats(),
                      members = Stats())
    return retval
    

