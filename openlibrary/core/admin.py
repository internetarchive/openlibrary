"""Admin functionality.
"""

import calendar
import datetime

import couchdb

from infogami import config


class Stats:
    def __init__(self, docs, key, total_key):
        self.key = key
        self.docs = docs
        self.latest = docs[-1].get(key, 0)
        self.previous = docs[-2].get(key, 0)
        try:
            # Last available total count
            self.total = (x for x in reversed(docs) if total_key in x).next()[total_key]
        except (KeyError, StopIteration):
            self.total = ""
                
    def get_counts(self, ndays = 28, times = False):
        """Returns the stats for last n days as an array useful for
        plotting. i.e. an array of [x, y] tuples where y is the value
        and `x` the x coordinate.

        If times is True, the x coordinate in the tuple will be
        timestamps for the day.
        """
        def _convert_to_milli_timestamp(d):
            """Uses the `_id` of the document `d` to create a UNIX
            timestamp and coverts it to milliseconds"""
            t = datetime.datetime.strptime(d, "counts-%Y-%m-%d")
            return calendar.timegm(t.timetuple()) * 1000

        if times:
            return [[_convert_to_milli_timestamp(x.id), x.get(self.key,0)] for x in self.docs[-ndays:]]
        else:
            return zip(range(0, ndays*5, 5),
                       (x.get(self.key, 0) for x in self.docs[-ndays:])) # The *5 and 5 are for the bar widths
        
    def get_summary(self, ndays = 28):
        """Returns the summary of counts for past n days.
        
        Summary can be either sum or average depending on the type of stats.
        This is used to find counts for last 7 days and last 28 days.
        """
        return sum(x[1] for x in self.get_counts(ndays))

            
def get_stats(ndays = 30):
    """Returns the stats for the past `ndays`"""
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
                  loans       = Stats(docs, "loans", "loans"),
                  members     = Stats(docs, "members", "total_members"),
                  works       = Stats(docs, "works", "total_works"),
                  editions    = Stats(docs, "editions", "total_editions"),
                  ebooks      = Stats(docs, "ebooks", "total_ebooks"),
                  covers      = Stats(docs, "covers", "total_covers"),
                  authors     = Stats(docs, "authors", "total_authors"),
                  subjects    = Stats(docs, "subjects", "total_subjects"))
    return retval
    

