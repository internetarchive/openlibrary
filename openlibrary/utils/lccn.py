import re

REV_RE = re.compile(r'rev.*')
REMOVESUFFIX_RE = re.compile(r'[^\/]+')
HYPHEN_RE = re.compile(r'(.+)-+([0-9]+)')
# Validates the syntax described at https://www.loc.gov/marc/lccn-namespace.html
LCCN_NORM_RE = re.compile(
    r'([a-z]|[a-z]?([a-z]{2}|[0-9]{2})|[a-z]{2}[0-9]{2})?[0-9]{8}$'
)


def normalize_lccn(lccn):
    lccn = lccn.strip().replace(' ', '')
    lccn = lccn.strip('-').lower()
    # remove any 'revised' text:
    lccn = REV_RE.sub('', lccn)
    m = REMOVESUFFIX_RE.match(lccn)
    lccn = m.group(0) if m else ''
    if hyph := HYPHEN_RE.match(lccn):
        lccn = hyph.group(1) + hyph.group(2).zfill(6)
    if LCCN_NORM_RE.match(lccn):
        return lccn
