import internetarchive as ia
import requests
from getpass import getpass

BWB_URL = 'https://www.betterworldbooks.com'


if __name__ == "__main__":
    data = {
        'user': 'openlibrary+sponsorship@archive.org',
        'password': getpass('password: ') 
    }
    s = requests.Session()
    s.post('%s/account/login' % BWB_URL, data=data)
    orders = s.get('%s/services/orders.aspx?op=History' % BWB_URL).json()
    order_ids = [order['OrderID'] for order in orders['Orders']]
    order_url = '%s/services/orders.aspx?op=Details&OrderID=%s' % (
        BWB_URL, order_ids[0])
    order = s.get(order_url).json()
    for item in order['Items']:
        i = ia.get_item('isbn_%s' % item['ISBN'].strip())
        i.modify_metadata(metadata={'book_price': int(item['Price'] * 100)})


    
