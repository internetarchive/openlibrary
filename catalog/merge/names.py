import re
from normalize import normalize

re_split_parts = re.compile('(.*?[. ]+)')
re_marc_name = re.compile('^(.*), (.*)$')

verbose = False

titles = frozenset([normalize(x) for x in 'Mrs', 'Sir', 'pseud', 'Lady', 'Baron', 'lawyer', 'Lord', 'actress', 'Dame', 'Mr', 'Viscount', 'professeur', 'Graf', 'Dr', 'Countess', 'Ministerialrat', 'Oberamtsrat', 'Rechtsanwalt'])

# marquis de

def flip_name(name):
    m = re_marc_name.match(name)
    if not m:
        return None
    return m.group(2) + ' ' + m.group(1)

def match_seq(parts1, parts2):
    if len(parts1) == len(parts2):
        return False
    if len(parts1) > len(parts2):
        longer, shorter = parts1, parts2
    else:
        longer, shorter = parts2, parts1

    i = 0
    for j in shorter:
        while not compare_part(j, longer[i]):
            i+=1
            if i >= len(longer):
                return False
    return True

def compare_part(p1, p2):
    p1 = normalize(p1)
    p2 = normalize(p2)
    return p1.startswith(p2) or p2.startswith(p1)

def compare_parts(parts1, parts2):
    if len(parts1) != len(parts2):
        return False
    for i, j in zip(parts1, parts2):
        if not compare_part(i, j):
            return False
    return True

def split_parts(s):
    parts = []
    m = re_split_parts.match(s)
    if not m:
        return [s.strip()]
    while m:
        end = m.end()
        parts.append(m.group(1).strip())
        m = re_split_parts.match(s, end)
    if end != len(s):
        parts.append(s[end:].strip())
    return parts

def amazon_title(amazon_first_parts, marc_first_parts):
    if normalize(amazon_first_parts[0]) not in titles:
        return False
    if compare_parts(marc_first_parts, amazon_first_parts[1:]):
        if verbose:
            print "match with Amazon title"
        return True
    if match_seq(marc_first_parts, amazon_first_parts[1:]):
        if verbose:
            print "partial match, with Amazon title"
        return True
    return False

def marc_title(amazon_first_parts, marc_first_parts):
#            print 'title found: ', marc_first_parts[-1]
    if normalize(marc_first_parts[-1]) not in titles:
        return False
    if compare_parts(marc_first_parts[:-1], amazon_first_parts):
        if verbose:
            print "match with MARC end title"
        return True
    if normalize(amazon_first_parts[0]) in titles:
        if compare_parts(marc_first_parts[:-1], amazon_first_parts[1:]):
            if verbose:
                print "match, both with titles"
            return True
        if match_seq(marc_first_parts[:-1], amazon_first_parts[1:]):
            if verbose:
                print "partial match, both with titles"
            return True
    if match_seq(marc_first_parts[:-1], amazon_first_parts):
        if verbose:
            print "partial match with MARC end title"
        return True
    if match_seq(marc_first_parts, amazon_first_parts):
        if verbose:
            print "partial match with MARC end title"
    return False

# use for person, org and event because the LC data says "Berkovitch, Israel." is an org
def match_name(amazon, marc):
    amazon_normalized = normalize(amazon)
    if amazon_normalized == normalize(marc):
        if verbose:
            print 'normalized names match'
        return True
    m = re_marc_name.match(marc)
    if not m:
        return False
    if amazon_normalized == normalize(m.group(1)):
        if verbose:
            print 'Amazon only has a last name, it matches MARC'
        return True
    if amazon_normalized == normalize(m.group(2) + ' ' + m.group(1)):
        if verbose:
            print 'match'
        return True
    if not (amazon.endswith(' ' + m.group(1)) \
            or amazon.endswith('.' + m.group(1))):
        if verbose:
            print 'Last name mismatch'
        return False
    marc_first_parts = split_parts(m.group(2))
    amazon_first_parts = split_parts(amazon[0:-(len(m.group(1))+1)])
    if compare_parts(marc_first_parts, amazon_first_parts):
        if verbose:
            print "match"
        return True
    if marc_title(amazon_first_parts, marc_first_parts):
        return True
    if amazon_title(amazon_first_parts, marc_first_parts):
        return True
    if match_seq(amazon_first_parts, marc_first_parts):
        if verbose:
            print "partial match"
        return True
    if verbose:
        print "no match"
    return False
