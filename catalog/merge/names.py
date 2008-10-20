import re
from normalize import normalize

re_split_parts = re.compile('(.*?[. ]+)')
re_marc_name = re.compile('^(.*), (.*)$')
re_amazon_space_name = re.compile('^(.+?[^ ]) +([A-Z][a-z]?)$')

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

def remove_trailing_dot(s):
    s = s.strip()
    if len(s) < 3 or not s.endswith('.') or s[-3] == ' ' or s[-3] == '.':
        return s
    return s[:-1]

def flip_marc_name(marc):
    m = re_marc_name.match(marc)
    if not m:
        return remove_trailing_dot(marc)
    first_parts = split_parts(m.group(2))
    if normalize(first_parts[-1]) not in titles: 
        # example: Eccles, David Eccles Viscount
        return remove_trailing_dot(m.group(2)) + ' ' + m.group(1)
    if len(first_parts) > 2 and normalize(first_parts[-2]) == normalize(m.group(1)):
        return u' '.join(first_parts[0:-1])
    return u' '.join(first_parts[:-1] + [m.group(1)])

def match_marc_name(marc1, marc2, last_name_only_ok):
    m1_normalized = normalize(marc1)
    m2_normalized = normalize(marc2)
    if m1_normalized == m2_normalized:
        return True
    m1 = re_marc_name.match(marc1)
    m2 = re_marc_name.match(marc2)
    if not m1:
        if m2 and marc1_normalized == normalize(m2.group(1)):
            return last_name_only_ok
        else:
            return False
    if not m2:
        if marc2_normalized == normalize(m1.group(1)):
            return last_name_only_ok
        else:
            return False
    if marc1_normalized == normalize(m2.group(2) + ' ' + m2.group(1)) or marc2_normalized == normalize(m1.group(2) + ' ' + m1.group(1)):
        return True
    if not (m1.group(1).endswith(' ' + m2.group(1)) or m1.endswith('.' + m2.group(1)) or \
            m2.group(1).endswith(' ' + m1.group(1)) or m2.endswith('.' + m1.group(1))):
        return False # Last name mismatch
    marc1_first_parts = split_parts(m1.group(2))
    marc2_first_parts = split_parts(m2.group(2))
    if compare_parts(marc1_first_parts, marc2_first_parts):
        return True
    if match_seq(marc1_first_parts, marc2_first_parts):
        return True
    if marc_title(marc1_first_parts, marc2_first_parts):
        return True
    if marc_title(marc2_first_parts, marc1_first_parts):
        return True
    if amazon_title(marc1_first_parts, marc2_first_parts):
        return True
    if amazon_title(marc2_first_parts, marc1_first_parts):
        return True
    return False

# try different combinations looking for a match
def match_name2(name1, name2):
    if name1 == name2:
        return True
    n1_normalized = normalize(name1)
    n2_normalized = normalize(name2)
    if n1_normalized == n2_normalized:
        return True
    n1_parts = split_parts(name1)
    n2_parts = split_parts(name2)
    if compare_parts(n1_parts, n2_parts):
        return True
    if match_seq(n1_parts, n2_parts):
        return True
    if marc_title(n1_parts, n2_parts):
        return True
    if marc_title(n2_parts, n1_parts):
        return True
    if amazon_title(n1_parts, n2_parts):
        return True
    if amazon_title(n2_parts, n1_parts):
        return True
    return False

def match_surname(surname, name):
    if name.endswith(' ' + surname) or name.endswith('.' + surname):
        return True
    surname = surname.replace(' ', '')
    if name.endswith(' ' + surname) or name.endswith('.' + surname):
        return True
    return False

def amazon_spaced_name(amazon, marc):
    len_amazon = len(amazon)
    if len_amazon != 30 and len_amazon != 31:
        return False
    m = re_amazon_space_name.search(amazon)
    if not m:
        return False
    amazon_surname = m.group(1)
    if normalize(amazon_surname) == normalize(marc):
        return True
    amazon_initals = m.group(2)
    m = re_marc_name.match(marc)
    if not m:
        return False
    marc_surname = m.group(1)
    if normalize(amazon_surname) != normalize(marc_surname):
        return False
    marc_first_parts = split_parts(m.group(2))
    amazon_first_parts = [x for x in amazon_initals]
    if compare_parts(marc_first_parts, amazon_first_parts):
        return True
    if match_seq(amazon_first_parts, marc_first_parts):
        return True
    return False

def match_name(amazon, marc, last_name_only_ok=True):
    if amazon_spaced_name(amazon, marc):
        return True
    amazon_normalized = normalize(amazon)
    amazon_normalized_no_space = normalize(amazon).replace(' ', '')
    marc_normalized = normalize(marc)
    # catches events and organizations
    if amazon_normalized == marc_normalized:
        if verbose:
            print 'normalized names match'
        return True
    if amazon_normalized_no_space == marc_normalized.replace(' ', ''):
        if verbose:
            print 'normalized, spaces removed, names match'
        return True
    # split MARC name
    m = re_marc_name.match(marc)
    if not m:
        return False
    surname = m.group(1)
    surname_no_space = surname.replace(' ', '')
    if amazon_normalized == normalize(surname) \
            or amazon_normalized_no_space == normalize(surname_no_space):
        if verbose:
            print 'Amazon only has a last name, it matches MARC'
        return last_name_only_ok
    if amazon_normalized == normalize(m.group(2) + ' ' + surname):
        if verbose:
            print 'match'
        return True
    if amazon_normalized_no_space == normalize(m.group(2) + surname).replace(' ', ''):
        if verbose:
            print 'match when spaces removed'
        return True
    if not match_surname(surname, amazon):
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

def match_not_just_surname(amazon, marc):
    return match_name(amazon, marc, last_name_only_ok=False)
