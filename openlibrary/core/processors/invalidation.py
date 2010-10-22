import web
import datetime
from infogami.infobase import client

from openlibrary.core import helpers as h

__all__ = [
    "InvalidationProcessor"
]

class InvalidationProcessor:
    """Application processor to invalidate/update locally cached documents.
    
    The openlibrary application caches some documents like templates, macros,
    javascripts etc. locally for variety of reasons. This class implements a
    way to make sure those documents are kept up-to-date with the db within
    some allowed constraints.
    
    This implements a kind of lazy consistancy, which guaranties the following:
    
    * If a client makes an update, he will continue to see that update on
      subsequent requests.
    * If a client sees an update made by somebody else, he will continue to
      see that update on subsequent requests.
    * A client sees older version of a doucment no longer than the specified
      timeout (in seconds) after the document is updated.
    
    It means that the following conditions will never happen:

    * A client edits a page and reloading the same page shows an older
      version.
    * A client loads a page and reloading the same page shows an older version.
    * A client continue to see an older version of a document for very long time.
    
    It is implemented as follows:

    * If there is an update, set a cookie with time of the update as value.
    * If the cookie timestamp is more than the last_poll_time, trigger reload.
    * If the cookie timestamp is less than the last_update_time, set the
      cookie with last_update_time.
    * If the current time is more than timeout seconds since last_poll_time,
      trigger reload.
      
    When the reload is triggered:
    * A request to the datebase is made to find list of documents modified after the last_poll_time. 
    * Trigger on_new_version event for each modified document. The application
      code that is handling the caching must listen to that event and
      invalidate/update its cached copy.
      
    How to use:
     
        from infogami.utils import delegate
        from infogami.infobase import client
        
        p = InvalidationProcessor(["/templates/", "/macros/"])
        
        # install the application processor
        delegate.app.add_processor(p)
        
        # add the hook to get notifications when a document is modified
        client.hooks.append(p.hook)
        
    Glossary:

    * cookie_timestamp: value of the invalidation cookie.
    * last_poll_time: timestamp of the latest reload
    * last_update_time: timestamp of the most recent update known to this
      process.
    """
    def __init__(self, prefixes, timeout=60, cookie_name="lastupdate"):
        self.prefixes = prefixes
        self.timeout = datetime.timedelta(0, timeout)

        self.cookie_name = cookie_name
        self.last_poll_time = datetime.datetime.utcnow()
        self.last_update_time = self.last_poll_time - self.timeout
        
        # set expire_time slightly more than timeout
        self.expire_time = 3 * timeout
        self.hook = _InvalidationHook(prefixes=prefixes, cookie_name=cookie_name, expire_time=self.expire_time)

    def __call__(self, handler):
        def t(date):
            return date.isoformat().split("T")[-1]
            
        log(web.ctx.method, web.ctx.fullpath, t(self.last_update_time), t(self.last_poll_time))
        
        cookie_time = self.get_cookie_time()
        
        # last update in recent timeout seconds?
        has_recent_update = (self.last_poll_time - self.last_update_time) < self.timeout
        print "has_recent_update", has_recent_update, self.last_poll_time - self.last_update_time
        
        if cookie_time and cookie_time > self.last_poll_time:
            log("cookie reload", cookie_time)
            self.reload()
        elif self.is_timeout():
            log("timeout reload")
            self.reload()
        elif has_recent_update and (cookie_time is None or cookie_time < self.last_update_time):
            log("setcookie", cookie_time, self.last_update_time)
            web.setcookie(self.cookie_name, self.last_update_time.isoformat(), expires=self.expire_time)

        return handler()

    def is_timeout(self):
        t = datetime.datetime.utcnow()
        dt = t - self.last_update_time
        return dt > self.timeout
        
    def get_cookie_time(self):
        cookies = web.cookies()

        if self.cookie_name in cookies:
            return self.parse_datetime(cookies[self.cookie_name])

    def parse_datetime(self, datestr):
        try:
            return h.parse_datetime(datestr)
        except ValueError:
            return None

    def reload(self):
        """Triggers on_new_version event for all the documents modified since last_poll_time.
        """
        t = datetime.datetime.utcnow()

        keys = []
        for prefix in self.prefixes:
            q = {"key~": prefix + "*", "last_modified>": self.last_poll_time.isoformat()}
            keys += things(q)
    
        log("reload", keys)
        if keys:
            web.ctx._invalidation_inprogress = True
            docs = get_many(keys)
            for doc in docs:
                try:
                    client._run_hooks("on_new_version", doc)
                except Exception:
                    pass
            del web.ctx._invalidation_inprogress

        self.last_poll_time = t
        
class _InvalidationHook:
    """Infogami client hook to get notification on edits. 
    
    This sets a cookie when any of the documents under the given prefixes is modified.
    """
    def __init__(self, prefixes, cookie_name, expire_time):
        self.prefixes = prefixes
        self.cookie_name = cookie_name
        self.expire_time = expire_time
        
    def __call__(self):
        return self
        
    def on_new_version(self, doc):
        if web.ctx.get("_invalidation_inprogress"):
            # This event is triggered from invalidation. ignore it.
            return
            
        print "on_new_version", doc.key
        if any(doc.key.startswith(prefix) for prefix in self.prefixes):
            # The supplied does doesn't have the updated last_modified time. 
            # Fetch the document afresh to get the correct last_modified time.
            doc = get_doc(doc.key)
            t = doc.last_modified
            
            log("hook setcookie", doc.key, t.isoformat())
            web.setcookie(self.cookie_name, t.isoformat(), expires=self.expire_time)
            
def get_doc(key):
    return web.ctx.site.get(key)
    
def get_many(keys):
    return web.ctx.site.get_many(keys)
    
def things(query):
    return web.ctx.site.things(query)
        
def log(*args):
    import os, sys
    args = [os.getpid()] + list(args)
    print >> sys.stderr, " ".join(str(a) for a in args)
