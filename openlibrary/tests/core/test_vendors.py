from dataclasses import dataclass
from unittest.mock import patch

import pytest

from openlibrary.core.vendors import (
    AmazonAPI,
    betterworldbooks_fmt,
    clean_amazon_metadata_for_load,
    get_amazon_metadata,
    is_dvd,
    split_amazon_title,
)


def test_clean_amazon_metadata_for_load_non_ISBN():
    # results from get_amazon_metadata() -> _serialize_amazon_product()
    # available from /prices?asin=B000KRRIZI
    amazon = {
        "publishers": ["Dutton"],
        "languages": [],
        "price_amt": "74.00",
        "source_records": ["amazon:B000KRRIZI"],
        "title": "The Man With the Crimson Box",
        "url": "https://www.amazon.com/dp/B000KRRIZI/?tag=internetarchi-20",
        "price": "$74.00 (used)",
        "number_of_pages": None,
        "cover": "https://images-na.ssl-images-amazon.com/images/I/31aTq%2BNA1EL.jpg",
        "qlt": "used",
        "physical_format": "hardcover",
        "edition": "First Edition",
        "publish_date": "1940",
        "authors": [{"name": "H.S. Keeler"}],
        "product_group": "Book",
        "offer_summary": {
            "total_used": 1,
            "total_new": 0,
            "total_collectible": 0,
            "lowest_used": 7400,
            "amazon_offers": 0,
        },
    }
    result = clean_amazon_metadata_for_load(amazon)
    # this result is passed to load() from vendors.create_edition_from_amazon_metadata()
    assert isinstance(result['publishers'], list)
    assert result['publishers'][0] == 'Dutton'
    assert (
        result['cover']
        == 'https://images-na.ssl-images-amazon.com/images/I/31aTq%2BNA1EL.jpg'
    )
    assert result['authors'][0]['name'] == 'H.S. Keeler'
    for isbn in ('isbn', 'isbn_10', 'isbn_13'):
        assert result.get(isbn) is None
    assert result['identifiers']['amazon'] == ['B000KRRIZI']
    assert result['source_records'] == ['amazon:B000KRRIZI']
    assert result['publish_date'] == '1940'


def test_clean_amazon_metadata_for_load_ISBN():
    amazon = {
        "publishers": ["Oxford University Press"],
        "price": "$9.50 (used)",
        "physical_format": "paperback",
        "edition": "3",
        "authors": [{"name": "Rachel Carson"}],
        "isbn_13": ["9780190906764"],
        "price_amt": "9.50",
        "source_records": ["amazon:0190906766"],
        "title": "The Sea Around Us",
        "url": "https://www.amazon.com/dp/0190906766/?tag=internetarchi-20",
        "offer_summary": {
            "amazon_offers": 1,
            "lowest_new": 1050,
            "total_new": 31,
            "lowest_used": 950,
            "total_collectible": 0,
            "total_used": 15,
        },
        "number_of_pages": "256",
        "cover": "https://images-na.ssl-images-amazon.com/images/I/51XKo3FsUyL.jpg",
        "languages": ["english"],
        "isbn_10": ["0190906766"],
        "publish_date": "Dec 18, 2018",
        "product_group": "Book",
        "qlt": "used",
    }
    result = clean_amazon_metadata_for_load(amazon)
    # TODO: implement and test edition number
    assert isinstance(result['publishers'], list)
    assert (
        result['cover']
        == 'https://images-na.ssl-images-amazon.com/images/I/51XKo3FsUyL.jpg'
    )
    assert result['authors'][0]['name'] == 'Rachel Carson'
    assert result.get('isbn') is None
    assert result.get('isbn_13') == ['9780190906764']
    assert result.get('isbn_10') == ['0190906766']
    assert result.get('identifiers') is None  # No Amazon id present
    assert result['source_records'] == ['amazon:0190906766']
    assert result['publish_date'] == 'Dec 18, 2018'
    assert result['physical_format'] == 'paperback'
    assert result['number_of_pages'] == '256'
    assert result.get('price') is None
    assert result.get('qlt') is None
    assert result.get('offer_summary') is None


def test_clean_amazon_metadata_for_load_translator():
    amazon = {
        "publishers": ["Oxford University Press"],
        "price": "$9.50 (used)",
        "physical_format": "paperback",
        "edition": "3",
        'authors': [{'name': 'Rachel Kushner'}],
        'contributors': [
            {'role': 'Translator', 'name': 'Suat Ertüzün'},
            {'role': 'Translator', 'name': 'Second Translator'},
        ],
        "isbn_13": ["9780190906764"],
        "price_amt": "9.50",
        "source_records": ["amazon:0190906766"],
        "title": "The Sea Around Us",
        "url": "https://www.amazon.com/dp/0190906766/?tag=internetarchi-20",
        "offer_summary": {
            "amazon_offers": 1,
            "lowest_new": 1050,
            "total_new": 31,
            "lowest_used": 950,
            "total_collectible": 0,
            "total_used": 15,
        },
        "number_of_pages": "256",
        "cover": "https://images-na.ssl-images-amazon.com/images/I/51XKo3FsUyL.jpg",
        "languages": ["english"],
        "isbn_10": ["0190906766"],
        "publish_date": "Dec 18, 2018",
        "product_group": "Book",
        "qlt": "used",
    }
    result = clean_amazon_metadata_for_load(amazon)
    # TODO: implement and test edition number
    assert isinstance(result['publishers'], list)
    assert (
        result['cover']
        == 'https://images-na.ssl-images-amazon.com/images/I/51XKo3FsUyL.jpg'
    )
    assert result['authors'][0]['name'] == 'Rachel Kushner'
    assert result['contributors'][0]['role'] == 'Translator'
    assert result['contributors'][0]['name'] == 'Suat Ertüzün'
    assert result['contributors'][1]['role'] == 'Translator'
    assert result['contributors'][1]['name'] == 'Second Translator'
    assert result.get('isbn') is None
    assert result.get('isbn_13') == ['9780190906764']
    assert result.get('isbn_10') == ['0190906766']
    assert result.get('identifiers') is None  # No Amazon id present
    assert result['source_records'] == ['amazon:0190906766']
    assert result['publish_date'] == 'Dec 18, 2018'
    assert result['physical_format'] == 'paperback'
    assert result['number_of_pages'] == '256'
    assert result.get('price') is None
    assert result.get('qlt') is None
    assert result.get('offer_summary') is None


amazon_titles = [
    # Original title, title, subtitle
    ['Test Title', 'Test Title', None],
    [
        'Killers of the Flower Moon: The Osage Murders and the Birth of the FBI',
        'Killers of the Flower Moon',
        'The Osage Murders and the Birth of the FBI',
    ],
    ['Pachinko (National Book Award Finalist)', 'Pachinko', None],
    ['Trapped in a Video Game (Book 1) (Volume 1)', 'Trapped in a Video Game', None],
    [
        "An American Marriage (Oprah's Book Club): A Novel",
        'An American Marriage',
        'A Novel',
    ],
    ['A Novel (German Edition)', 'A Novel', None],
    [
        'Vietnam Travel Guide 2019: Ho Chi Minh City - First Journey : 10 Tips For an Amazing Trip',
        'Vietnam Travel Guide 2019 : Ho Chi Minh City - First Journey',
        '10 Tips For an Amazing Trip',
    ],
    [
        'Secrets of Adobe(r) Acrobat(r) 7. 150 Best Practices and Tips (Russian Edition)',
        'Secrets of Adobe Acrobat 7. 150 Best Practices and Tips',
        None,
    ],
    [
        'Last Days at Hot Slit: The Radical Feminism of Andrea Dworkin (Semiotext(e) / Native Agents)',
        'Last Days at Hot Slit',
        'The Radical Feminism of Andrea Dworkin',
    ],
    [
        'Bloody Times: The Funeral of Abraham Lincoln and the Manhunt for Jefferson Davis',
        'Bloody Times',
        'The Funeral of Abraham Lincoln and the Manhunt for Jefferson Davis',
    ],
]


@pytest.mark.parametrize(("amazon", "title", "subtitle"), amazon_titles)
def test_split_amazon_title(amazon, title, subtitle):
    assert split_amazon_title(amazon) == (title, subtitle)


def test_clean_amazon_metadata_for_load_subtitle():
    amazon = {
        "publishers": ["Vintage"],
        "price": "$4.12 (used)",
        "physical_format": "paperback",
        "edition": "Reprint",
        "authors": [{"name": "David Grann"}],
        "isbn_13": ["9780307742483"],
        "price_amt": "4.12",
        "source_records": ["amazon:0307742482"],
        "title": "Killers of the Flower Moon: The Osage Murders and the Birth of the FBI",
        "url": "https://www.amazon.com/dp/0307742482/?tag=internetarchi-20",
        "offer_summary": {
            "lowest_new": 869,
            "amazon_offers": 1,
            "total_new": 57,
            "lowest_used": 412,
            "total_collectible": 2,
            "total_used": 133,
            "lowest_collectible": 1475,
        },
        "number_of_pages": "400",
        "cover": "https://images-na.ssl-images-amazon.com/images/I/51PP3iTK8DL.jpg",
        "languages": ["english"],
        "isbn_10": ["0307742482"],
        "publish_date": "Apr 03, 2018",
        "product_group": "Book",
        "qlt": "used",
    }
    result = clean_amazon_metadata_for_load(amazon)
    assert result['title'] == 'Killers of the Flower Moon'
    assert result.get('subtitle') == 'The Osage Murders and the Birth of the FBI'
    assert (
        result.get('full_title')
        == 'Killers of the Flower Moon : The Osage Murders and the Birth of the FBI'
    )
    # TODO: test for, and implement languages


def test_betterworldbooks_fmt():
    isbn = '9780393062274'
    bad_data = betterworldbooks_fmt(isbn)
    assert bad_data.get('isbn') == isbn
    assert bad_data.get('price') is None
    assert bad_data.get('price_amt') is None
    assert bad_data.get('qlt') is None


# Test cases to add:
# Multiple authors


def test_get_amazon_metadata() -> None:
    """
    Mock a reply from the Amazon Products API so we can do a basic test for
    get_amazon_metadata() and cached_get_amazon_metadata().
    """

    class MockRequests:
        def get(self):
            pass

        def raise_for_status(self):
            return True

        def json(self):
            return mock_response

    mock_response = {
        'status': 'success',
        'hit': {
            'url': 'https://www.amazon.com/dp/059035342X/?tag=internetarchi-20',
            'source_records': ['amazon:059035342X'],
            'isbn_10': ['059035342X'],
            'isbn_13': ['9780590353427'],
            'price': '$5.10',
            'price_amt': 509,
            'title': "Harry Potter and the Sorcerer's Stone",
            'cover': 'https://m.media-amazon.com/images/I/51Wbz5GypgL._SL500_.jpg',
            'authors': [{'name': 'Rowling, J.K.'}, {'name': 'GrandPr_, Mary'}],
            'publishers': ['Scholastic'],
            'number_of_pages': 309,
            'edition_num': '1',
            'publish_date': 'Sep 02, 1998',
            'product_group': 'Book',
            'physical_format': 'paperback',
        },
    }
    expected = {
        'url': 'https://www.amazon.com/dp/059035342X/?tag=internetarchi-20',
        'source_records': ['amazon:059035342X'],
        'isbn_10': ['059035342X'],
        'isbn_13': ['9780590353427'],
        'price': '$5.10',
        'price_amt': 509,
        'title': "Harry Potter and the Sorcerer's Stone",
        'cover': 'https://m.media-amazon.com/images/I/51Wbz5GypgL._SL500_.jpg',
        'authors': [{'name': 'Rowling, J.K.'}, {'name': 'GrandPr_, Mary'}],
        'publishers': ['Scholastic'],
        'number_of_pages': 309,
        'edition_num': '1',
        'publish_date': 'Sep 02, 1998',
        'product_group': 'Book',
        'physical_format': 'paperback',
    }
    isbn = "059035342X"
    with (
        patch("requests.get", return_value=MockRequests()),
        patch("openlibrary.core.vendors.affiliate_server_url", new=True),
    ):
        got = get_amazon_metadata(id_=isbn, id_type="isbn")
        assert got == expected


@dataclass
class ProductGroup:
    display_value: str | None


@dataclass
class Binding:
    display_value: str | None


@dataclass
class Classifications:
    product_group: ProductGroup | None
    binding: Binding


@dataclass
class Contributor:
    locale: str | None
    name: str | None
    role: str | None


@dataclass
class ByLineInfo:
    brand: str | None
    contributors: list[Contributor] | None
    manufacturer: str | None


@dataclass
class ItemInfo:
    classifications: Classifications | None
    content_info: str
    by_line_info: ByLineInfo | None
    title: str


@dataclass
class AmazonAPIReply:
    item_info: ItemInfo
    images: str
    offers: str
    asin: str


@pytest.mark.parametrize(
    ("product_group", "expected"),
    [
        ('dvd', {}),
        ('DVD', {}),
        ('Dvd', {}),
    ],
)
def test_clean_amazon_metadata_does_not_load_DVDS_product_group(
    product_group, expected
) -> None:
    """Ensure data load does not load dvds and relies on fake API response objects"""
    dvd_product_group = ProductGroup(product_group)
    classification = Classifications(
        product_group=dvd_product_group, binding=Binding('')
    )
    item_info = ItemInfo(
        classifications=classification, content_info='', by_line_info=None, title=''
    )
    amazon_metadata = AmazonAPIReply(
        item_info=item_info,
        images='',
        offers='',
        asin='',
    )
    result = AmazonAPI.serialize(amazon_metadata)
    assert result == expected


def test_serialize_does_not_load_translators_as_authors() -> None:
    """Ensure data load does not load translators as author and relies on fake API response objects"""
    classification = None
    contributors = [
        Contributor(None, 'Rachel Kushner', 'Author'),
        Contributor(None, 'Suat Ertüzün', 'Translator'),
        Contributor(None, 'Second Translator', 'Translator'),
        Contributor(None, 'No Role', ''),
        Contributor(None, 'Third Contributor', 'Unsupported Role'),
    ]
    by_line_info = ByLineInfo(None, contributors, None)
    item_info = ItemInfo(
        classifications=classification,
        content_info='',
        by_line_info=by_line_info,
        title='',
    )
    amazon_metadata = AmazonAPIReply(
        item_info=item_info,
        images='',
        offers='',
        asin='',
    )
    result = AmazonAPI.serialize(amazon_metadata)
    expected = {
        'url': 'https://www.amazon.com/dp//?tag=',
        'source_records': ['amazon:'],
        'isbn_10': [''],
        'isbn_13': [],
        'price': '',
        'price_amt': '',
        'title': '',
        'cover': None,
        'authors': [{'name': 'Rachel Kushner'}],
        'contributors': [
            {'role': 'Translator', 'name': 'Suat Ertüzün'},
            {'role': 'Translator', 'name': 'Second Translator'},
        ],
        'publishers': [],
        'number_of_pages': '',
        'edition_num': '',
        'publish_date': '',
        'product_group': None,
        'physical_format': None,
    }
    assert result == expected


@pytest.mark.parametrize(
    ("physical_format", "expected"),
    [
        ('dvd', {}),
        ('DVD', {}),
        ('Dvd', {}),
    ],
)
def test_clean_amazon_metadata_does_not_load_DVDS_physical_format(
    physical_format, expected
) -> None:
    dvd_product_group = ProductGroup('isolate_physical_format')
    binding = Binding(physical_format)
    classification = Classifications(product_group=dvd_product_group, binding=binding)
    item_info = ItemInfo(
        classifications=classification, content_info='', by_line_info=None, title=''
    )
    amazon_metadata = AmazonAPIReply(
        item_info=item_info,
        images='',
        offers='',
        asin='',
    )
    result = AmazonAPI.serialize(amazon_metadata)
    assert result == expected


@pytest.mark.parametrize(
    ("physical_format", "product_group", "expected"),
    [
        ('dvd', 'dvd', True),
        (None, None, False),
        ('Book', 'Book', False),
        ('DVD', None, True),
        ('Dvd', None, True),
        ('dvd', None, True),
        ('Book', 'dvd', True),
        (None, 'dvd', True),
        (None, 'Book', False),
        ('dvd', 'book', True),
    ],
)
def test_is_dvd(physical_format, product_group, expected):
    book = {
        'physical_format': physical_format,
        'product_group': product_group,
    }

    got = is_dvd(book)
    assert got is expected
