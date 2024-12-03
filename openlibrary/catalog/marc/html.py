import re

from pymarc.record import Record

trans = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '\n': '<br>', '\x1b': '<b>[esc]</b>'}
re_html_replace = re.compile('([&<>\n\x1b])')


def esc(s):
    return re_html_replace.sub(lambda m: trans[m.group(1)], s)


def subfields(line):
    if isinstance(line, str):
        return esc(line)
    return f"{line['ind1']}{line['ind2']} " + ''.join(
        [f'<b>${k}</b>{esc(v)}' for s in line['subfields'] for k, v in s.items()]
    )


class html_record:
    def __init__(self, data):
        assert len(data) == int(data[:5])
        self.data = data
        self.record = Record(data)
        self.leader = self.record.leader

    def html(self):
        return '<br>\n'.join(
            [
                f'<b>{tag}</b> <code>{subfields(value)}</code>'
                for r in self.record.as_dict()['fields']
                for tag, value in r.items()
            ]
        )
