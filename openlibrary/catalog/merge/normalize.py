import re
import unicodedata

import six

#re_brace = re.compile('{[^{}]+?}')
re_normalize = re.compile('[^[:alpha:] ]', re.I)
re_whitespace_and_punct = re.compile(r'[-\s,;:.]+')

def normalize(s):
    """
    Normalizes title by lowercasing, unicode -> NFC,
    stripping extra whitespace and punctuation, and replacing ampersands.
    :param str s:
    :rtype: str
    """

    if isinstance(s, six.text_type):
        # LATIN SMALL LETTER L WITH STROKE' (U+0142) -> 'l'
        s = unicodedata.normalize('NFC', s.replace(u'\u0142', u'l'))
    s = s.replace(' & ', ' and ')
    # remove {mlrhring} and friends
    # see http://www.loc.gov/marc/mnemonics.html
    # s = re_brace.sub('', s)
    s = re_whitespace_and_punct.sub(' ', s.lower())
    s = re_normalize.sub('', s.strip())
    return s
