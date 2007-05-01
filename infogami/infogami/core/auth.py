import db
import time, datetime
import hmac
import web
import urllib

SECRET = "ofu889e4i5kfem" #@@ make configurable

def setcookie(user, remember=False):
    t = datetime.datetime(*time.gmtime()[:6]).isoformat()
    text = "%d,%s" % (user.id, t)
    text += "," + _digest(text)

    expires = (remember and 3600*24*7) or ""
    web.setcookie("infogami_session", text, expires=expires)
    
def get_user():
    """Returns the current user from the session."""
    session = web.cookies(infogami_session=None).infogami_session
    if session:
        user_id, login_time, digest = session.split(',')
        if _digest(user_id + "," + login_time) == digest:
            return db.get_user(int(user_id))

def _digest(text):
    return hmac.HMAC(SECRET, text).hexdigest()

def require_login(f):
    def g(*a, **kw):
        if not get_user():
            return login_redirect()
        return f(*a, **kw)
        
    return g

def login_redirect(path=None):
    if path is None:
        path = web.ctx.path
    
    query = urllib.urlencode({"redirect":path})
    web.seeother(web.ctx.homepath + "/login?" + query)
    raise StopIteration
