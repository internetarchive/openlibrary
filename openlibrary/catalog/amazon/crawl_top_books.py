from openlibrary.catalog.amazon.crawl import read_page, write_books, get_url, get_cats

def get_serp():
    params = 'i:stripbooks,n:!1000,p_n_feature_browse-bin:618083011'

    #crawled = set(i[:-1] for i in open('/2/edward/amazon/crawled'))

    total, books, cats = read_page(params)
    print 'total:', total, 'number of books:', len(books), 'number of cats:', len(cats)

#get_serp()

params = 'i:stripbooks,n:9988'
root = get_url(params)
cats = get_cats(root)

for a, b, c in cats:
    print "%8d %-30s %8d" % (a, b, c)

#books = [i[:-1] for i in open('/2/edward/amazon/best_sellers2')]
#write_books(books)
