import csv
from openlibrary.catalog.title_page_img.load import add_cover_image

input_file = 'smashwords_ia_20110325-extended-20110406.csv'

headings = None
for row in csv.reader(open(input_file)):
    if not headings:
        headings = row
        print row
        continue
    book = dict(zip(headings, [s.decode('utf-8') for s in row]))

    isbn = book['ISBN']

    ia = isbn if isbn else 'SW000000' + book['SWID']

    q = {'type':'/type/edition', 'ocaid': ia, 'works': None}
    existing = list(ol.query(q))
    print (existing[0]['key'], ia)
    add_cover_image(existing[0]['key'], ia)
