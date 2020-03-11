from openlibrary.catalog.marc.fast_parse import get_all_tag_lines, translate, split_line
import re

trans = {'&':'&amp;','<':'&lt;','>':'&gt;','\n':'<br>', '\x1b': '<b>[esc]</b>'}
re_html_replace = re.compile('([&<>\n\x1b])')

def esc(s):
    return re_html_replace.sub(lambda m: trans[m.group(1)], s)

def esc_sp(s):
    return esc(s).replace(' ', '&nbsp;')

class html_record():
    def __init__(self, data):
        """
        >>> hr = html_record("00053This is the leader.Now we are beyond the leader.")
        >>> hr.leader
        '00053This is the leader.'
        >>> hr.is_marc8
        True
        >>> # Change "00053" to "00054"...
        >>> hr = html_record("00054This is the leader.Now we are beyond the leader.")
        Traceback (most recent call last):
        ...
        AssertionError
        >>> # Change " " to "a"...
        >>> hr = html_record("00053Thisais the leader.Now we are beyond the leader.")
        >>> hr.is_marc8
        False
        """
        assert len(data) == int(data[:5])
        self.data = data
        self.leader = data[:24]
        self.is_marc8 = data[9] != 'a'

    def html(self):
        return '<br>\n'.join(self.html_line(t, l) for t, l in get_all_tag_lines(self.data))

    def html_subfields(self, line):
        assert line[-1] == '\x1e'
        encode = {
            'k': lambda s: '<b>$%s</b>' % esc(translate(s, self.is_marc8)),
            'v': lambda s: esc(translate(s, self.is_marc8)),
        }
        return ''.join(encode[k](v) for k, v in split_line(line[2:-1]))

    def html_line(self, tag, line):
        if tag.startswith('00'):
            s = esc_sp(line[:-1])
        else:
            s = esc_sp(line[0:2]) + ' ' + self.html_subfields(line)
        return u'<large>' + tag + u'</large> <code>' + s + u'</code>'


if __name__ == '__main__':
    import doctest

    doctest.testmod()
