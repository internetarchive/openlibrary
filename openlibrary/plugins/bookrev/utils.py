import web
from infogami.core import auth

def require_user(f):
    def g(*a, **kw):    
        self, site, params = a[0], a[1], a[2:]
        user = auth.get_user(site)
        if user:
            a = [self, site, user] + list(params)
            return f(*a, **kw)
        else:            
            return web.redirect('/account/login')
    return g

def lpad(s, lpad):
    if not s:
        return lpad
    elif s.startswith(lpad):
        return s
    else:
        return '%s%s' % (lpad, s)

def read_text():
    lines = []
    line = raw_input()
    while line:
        lines.append(line)
        line = raw_input()
    return "\n\n".join(lines)
