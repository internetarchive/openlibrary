import requests

r = requests.get('https://citapress.org/page-data/index/page-data.json')
data = (
    r.json()
)  # we load the fetched website data into python as json which we can manipulate like a dictionary
books = data['result']['data']['allMarkdownRemark']['nodes']

# We need these books to be converted into this format: https://github.com/internetarchive/openlibrary-client/blob/master/olclient/schemata/import.schema.json
penlibrary_books = [
    {
        'title': book['frontmatter']['title'],
        'description': book['frontmatter']['description'],
        'cover': '???',
        "source_records": 'citapress',  # ignore, leave as is :)
        "authors": [],  # might be missing from the data!
        "publishers": [],
        "publish_date": '',
    }
    for book in books
]
