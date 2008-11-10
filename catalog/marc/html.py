from catalog.marc.fast_parse import get_all_tag_lines, get_all_subfields
import re

trans = {'&':'amp','<':'lt','>':'gt','\n':'<br>'}
re_html_replace = re.compile('([&<>])')

re_subtag = re.compile('\x1f(.?)')

def esc(s):
    return re_html_replace.sub(lambda m: "&%s;" % trans[m.group(1)], s.encode('utf8'))

def esc_sp(s):
    return esc(s).replace(' ', '&nbsp;')

def html_subfields(line):
    assert line[-1] == '\x1e'
    return re_subtag.sub(lambda m: '<b>$%s</b>' % m.group(1), esc(line[2:-1]))

def html_line(tag, line):
    return '<large>' + tag + '</large> <code>' + (esc(line[:-1])
        if tag.startswith('00')
        else esc_sp(line[0:2]) + ' ' + html_subfields(line)) + '</code>'

def as_html(data):
    return '<br>\n'.join(html_line(t, l) for t, l in get_all_tag_lines(data))

class html_record():
    def __init__(self, data):
        self.data = data
        self.leader = data[:24]
    def html(self):
        return as_html(self.data) 

def test_html_subfields():
    samples = [
        ('  \x1fa0123456789\x1e', '<b>$a</b>0123456789'),
        ('  end of wrapped\x1e', 'end of wrapped'),
        ('  \x1fa<whatever>\x1e', '<b>$a</b>&lt;whatever&gt;'),
    ]
    for input, output in samples:
        assert html_subfields(input) == output

def test_html_line():
    samples = [
        ('020', '  \x1fa0123456789\x1e', '&nbsp;&nbsp; <b>$a</b>0123456789'),
        ('520', '  end of wrapped\x1e', '&nbsp;&nbsp; end of wrapped')
    ]

    for tag, input, output in samples:
        expect = '<large>%s</large> <code>%s</code>' % (tag, output)
        assert html_line(tag, input) == expect
