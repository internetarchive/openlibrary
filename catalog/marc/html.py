from catalog.marc.fast_parse import get_all_tag_lines, get_all_subfields
import re

trans = {'&':'amp','<':'lt','>':'gt','\n':'<br>'}
re_html_replace = re.compile('([&<>])')

def esc(s):
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s.encode('utf8'))

def esc_sp(s):
    return esc.replace(' ', '&nbsp;')

def as_html(data):
    ret = []
    for tag, line in get_all_tag_lines(data):
        cur = '<large>%s</large>' % tag
        if tag.startswith('00'): # control field:
            cur += '<code>%s</code>\n' % esc(line[:-1])
        else:
            cur += '<code>' + esc_sp(line[0:2]) + ''.join("<b>$%s</b>%s" % (esc_sp(k), esc(v)) for k, v in get_all_subfields(line)) + '</code>'
        ret.append(cur)
    return '<br>\n'.join(ret)

class html_record():
    def __init__(self, data):
        self.data = data
        self.leader = data[:24]
    def html(self):
        return as_html(self.data) 
