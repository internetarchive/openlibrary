import pytest

from openlibrary.catalog.marc.html import html_record


def test_html_subfields():
    samples = [
        ('  \x1fa0123456789\x1e', '<b>$a</b>0123456789'),
        ('  end of wrapped\x1e', 'end of wrapped'),
        ('  \x1fa<whatever>\x1e', '<b>$a</b>&lt;whatever&gt;'),
    ]
    hr = html_record("00053This is the leader.Now we are beyond the leader.")
    for input, output in samples:
        assert hr.html_subfields(input) == output


@pytest.mark.xfail(reason='As discussed in #3071, the encoding (marc8 or utf8) is '
                          'not defined for a single field.  To be fixed by #3057.')
def test_html_line():
    samples = [
        ('020', '  \x1fa0123456789\x1e', '&nbsp;&nbsp; <b>$a</b>0123456789'),
        ('520', '  end of wrapped\x1e', '&nbsp;&nbsp; end of wrapped'),
        ('245', ('10\x1faDbu ma la \xca\xbejug pa\xca\xbei kar t\xcc\xa3i\xcc\x84k '
                 ':\x1fbDwags-brgyud grub pa\xca\xbei s\xcc\x81in\xcc\x87 rta /\x1f'
                 'cKarma-pa Mi-bskyod-rdo-rje.\x1e'),
                (u'10 <b>$a</b>Dbu ma la \u02bejug pa\u02bei kar \u1e6d\u012bk :<b>'
                 u'$b</b>Dwags-brgyud grub pa\u02bei \u015bi\u1e45 rta /<b>$c</b>Ka'
                 u'rma-pa Mi-bskyod-rdo-rje.')),
    ]
    hr = html_record("00053This is the leader.Now we are beyond the leader.")
    for tag, input, output in samples:
        expect = '<large>%s</large> <code>%s</code>' % (tag, output)
        assert hr.html_line(tag, input) == expect
