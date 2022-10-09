from openlibrary.catalog.marc.html import html_record


def test_html_subfields():
    samples = [
        (b'  \x1fa0123456789\x1e', '<b>$a</b>0123456789'),
        (b'  end of wrapped\x1e', 'end of wrapped'),
        (b'  \x1fa<whatever>\x1e', '<b>$a</b>&lt;whatever&gt;'),
    ]
    hr = html_record(b'00053This is the leader.Now we are beyond the leader.')
    for input_, output in samples:
        assert hr.html_subfields(input_) == output


def test_html_line_marc8():
    samples = [
        (b'020', b'  \x1fa0123456789\x1e', '&nbsp;&nbsp; <b>$a</b>0123456789'),
        (b'520', b'  end of wrapped\x1e', '&nbsp;&nbsp; end of wrapped'),
    ]
    hr = html_record(b'00053This is the leader.Now we are beyond the leader.')
    for tag, input_, output in samples:
        expect = '<large>{}</large> <code>{}</code>'.format(tag.decode('utf-8'), output)
        assert hr.html_line(tag, input_) == expect


def test_html_line_utf8():
    samples = [
        (
            b'245',
            (
                b'10\x1faDbu ma la \xca\xbejug pa\xca\xbei kar t\xcc\xa3i\xcc\x84k '
                b':\x1fbDwags-brgyud grub pa\xca\xbei s\xcc\x81in\xcc\x87 rta /\x1f'
                b'cKarma-pa Mi-bskyod-rdo-rje.\x1e'
            ),
            (
                '10 <b>$a</b>Dbu ma la \u02bejug pa\u02bei kar \u1e6d\u012bk :<b>'
                '$b</b>Dwags-brgyud grub pa\u02bei \u015bi\u1e45 rta /<b>$c</b>Ka'
                'rma-pa Mi-bskyod-rdo-rje.'
            ),
        ),
    ]
    hr = html_record(b'00053Thisais the leader.Now we are beyond the leader.')
    assert hr.is_marc8 is False
    for tag, input_, output in samples:
        expect = '<large>{}</large> <code>{}</code>'.format(tag.decode('utf-8'), output)
        assert hr.html_line(tag, input_) == expect
