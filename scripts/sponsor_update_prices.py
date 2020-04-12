"""This script programatically iterates over each
item in the bwb purchase receipt and update the archive.org item with the
correct `book_price`.

NB:
- This script requires manually inputting the password for our bwb account.
- The script automatically fetches + processes the latest receipt (no
  choice is provided)

Background:
When a book is sponsored, a stub-item is created on Archive.org with
the format archive.org/details/isbn_{isbn}. Metadata is written into
the item, such as the price the patron has paid for the book (in
cents), i.e. `est_book_price`. Once the book is purchased, we write
back this number into the archive.org item's metadata as `book_price`
(cents). We used to do this manually. Then we discovered that from
betterworldbooks.com/account (when logged in) there is a way to get a
json feed of all of the prices, and update IA items using @jake's tool.


https://tinyurl.com/book-sponsorship-procedure
"""

import internetarchive as ia
import requests
from getpass import getpass

BWB_URL = 'https://www.betterworldbooks.com'


if __name__ == "__main__":
    s = requests.Session()
    s.post('%s/account/login' % BWB_URL, data={
        'user': 'openlibrary+sponsorship@archive.org',
        'password': getpass('password: '),
    })
    orders = s.get('%s/services/orders.aspx?op=History' % BWB_URL).json()
    order_ids = [order['OrderID'] for order in orders['Orders']]
    # NB: We select the *last
    order_url = '%s/services/orders.aspx?op=Details&OrderID=%s' % (
        BWB_URL, order_ids[0])
    order = s.get(order_url).json()
    for item in order['Items']:
        ocaid = 'isbn_%s' % item['ISBN'].strip()
        print(ocaid)
        i = ia.get_item(ocaid)
        i.modify_metadata(metadata={'book_price': int(item['Price'] * 100)})
