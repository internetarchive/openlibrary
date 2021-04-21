from openlibrary.catalog.marc.fast_parse import get_all_tag_lines, translate, split_line
import re

trans = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '\n': '<br>', '\x1b': '<b>[esc]</b>'}
re_html_replace = re.compile('([&<>\n\x1b])')


def esc(s):
    return re_html_replace.sub(lambda m: trans[m.group(1)], s)


def esc_sp(s):
    return esc(s).replace(' ', '&nbsp;')


class html_record:
    def __init__(self, data):
        assert len(data) == int(data[:5])
        self.data = data
        self.leader = data[:24].decode('utf-8', errors='replace')
        self.is_marc8 = self.leader[9] != u'a'

    def html(self):
        return '<br>\n'.join(
            self.html_line(t, l) for t, l in get_all_tag_lines(self.data)
        )

    def html_subfields(self, line):
        assert line[-1] == b'\x1e'[0]
        encode = {
            'k': lambda s: '<b>$%s</b>' % esc(translate(s, self.is_marc8)),
            'v': lambda s: esc(translate(s, self.is_marc8)),
        }
        return ''.join(encode[k](v) for k, v in split_line(line[2:-1]))

    def html_line(self, tag, line):
        tag = tag.decode('utf-8')
        if tag.startswith('00'):
            s = esc_sp(line[:-1].decode('utf-8', errors='replace'))
        else:
            s = (
                esc_sp(line[0:2].decode('utf-8', errors='replace'))
                + ' '
                + self.html_subfields(line)
            )
        return u'<large>' + tag + u'</large> <code>' + s + u'</code>'
