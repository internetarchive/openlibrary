import re

re_normalize = re.compile('[^\w ]')
re_whitespace = re.compile('[-\s,.]+')

def normalize(s):
    if isinstance(s, unicode):
        s = s.replace(u'\u0142', u'l')
    s = s.replace(' & ', ' and ')
    s = re_whitespace.sub(' ', s.lower())
    s = re_normalize.sub('', s.strip())
    return s


