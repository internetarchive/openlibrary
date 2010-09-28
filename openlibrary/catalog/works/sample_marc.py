from catalog.marc.all import iter_marc
import re

# random authors and subjects
terms = [
    'rowling', 'harry potter', 'shakespeare', 'hamlet', 'twain', 'darwin', 
    'sagan', 'huckleberry finn', 'tom sawyer', 'verne', 'waiting for godot', 
    'beckett', 'churchill', 'darwin', 'dickens', 'doyle', 'leonardo',
    'da vinci',
]

re_terms = re.compile('(' + '|'.join(terms) + ')', re.I)

out = open('/1/pharos/edward/sample_marc2', 'w')
for rec_no, pos, loc, data in iter_marc():
    if re_terms.search(data):
        print >> out, (loc, data)
out.close()
