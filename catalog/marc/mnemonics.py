# read MARC mnemonics
# result is in MARC8 and still needs to be converted to Unicode

import re

re_brace = re.compile('(\{.+?\})')

def load_table(filename):
    mapping = {}
    for line in (i.split(",") for i in open(filename) if i.startswith("{")):
        key = line[0]
        value = ""
        for d in line[2].strip().split(" "):
            assert len(d) == 4
            assert d[3] == 'd'
            value += chr(int(d[0:3]))

        mapping[key] = value
    return mapping

mapping = load_table("marc21.txt")

def test_read():
    input = 'Tha{mllhring}{macr}alib{macr}i, {mllhring}Abd al-Malik ibn Mu{dotb}hammad,'
    output = 'Tha\xb0\xe5alib\xe5i, \xb0Abd al-Malik ibn Mu\xf2hammad,'
    assert read(input) == output

def read(input):
    return re_brace.sub(lambda x: mapping[x.group(1)], input)
