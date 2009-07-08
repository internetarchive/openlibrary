# find fields in amazon data that don't appear in MARC data, extract and store in shelve

import shelve

seg_file = '/home/edward/ol/amazon/seg/22'

match = set(eval(line)[0] \
    for line \
    in open('/home/edward/ol/merge/amazon_marc/amazon_lc_map'))

# fields that MARC is missing:
# binding
# subject
# category
# series
# series_num
# edition
# dimensions
# first_sentence
# sip []
# cap []
# shipping_weight

fields = [ 'binding', 'subject', 'category', 'series', 'series_num', 'edition',\
    'dimensions', 'first_sentence', 'sip', 'cap', 'shipping_weight' ]

d = shelve.open('amazon_fields.shelve', protocol=-1, writeback=True)

for line in open(seg_file):
    isbn, item = eval(line)
    if isbn not in match:
        continue
    d[isbn] = dict([(f, item[f]) for f in fields if f in item])
d.close
