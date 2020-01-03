import pytest
import re
import requests
from openlibrary.core.vendors import (
    split_amazon_title, clean_amazon_metadata_for_load,
    _get_betterworldbooks_thirdparty_metadata, BWB_URL,
    betterworldbooks_fmt)

def test_clean_amazon_metadata_for_load_non_ISBN():
    # results from get_amazon_metadata() -> _serialize_amazon_product()
    # available from /prices?asin=B000KRRIZI
    amazon = {"publishers": ["Dutton"], "languages": [], "price_amt": "74.00", "source_records": ["amazon:B000KRRIZI"], "title": "The Man With the Crimson Box", "url": "https://www.amazon.com/dp/B000KRRIZI/?tag=internetarchi-20", "price": "$74.00 (used)", "number_of_pages": None, "cover": "https://images-na.ssl-images-amazon.com/images/I/31aTq%2BNA1EL.jpg", "qlt": "used", "physical_format": "hardcover", "edition": "First Edition", "publish_date": "1940", "authors": [{"name": "H.S. Keeler"}], "product_group": "Book", "offer_summary": {"total_used": 1, "total_new": 0, "total_collectible": 0, "lowest_used": 7400, "amazon_offers": 0}}

    result = clean_amazon_metadata_for_load(amazon)
    # this result is passed to load() from vendors.create_edition_from_amazon_metadata()
    assert isinstance(result['publishers'], list)
    assert result['publishers'][0] == 'Dutton'
    assert result['cover'] == 'https://images-na.ssl-images-amazon.com/images/I/31aTq%2BNA1EL.jpg'
    assert result['authors'][0]['name'] == 'H.S. Keeler'
    assert result.get('isbn') is None
    assert result.get('isbn_13') is None
    assert result.get('isbn_10') is None
    assert result['identifiers']['amazon'] == ['B000KRRIZI']
    assert result['source_records'] == ['amazon:B000KRRIZI']
    assert result['publish_date'] == '1940'


def test_clean_amazon_metadata_for_load_ISBN():
    amazon =  {"publishers": ["Oxford University Press"], "price": "$9.50 (used)", "physical_format": "paperback", "edition": "3", "authors": [{"name": "Rachel Carson"}], "isbn_13": ["9780190906764"], "price_amt": "9.50", "source_records": ["amazon:0190906766"], "title": "The Sea Around Us", "url": "https://www.amazon.com/dp/0190906766/?tag=internetarchi-20", "offer_summary": {"amazon_offers": 1, "lowest_new": 1050, "total_new": 31, "lowest_used": 950, "total_collectible": 0, "total_used": 15}, "number_of_pages": "256", "cover": "https://images-na.ssl-images-amazon.com/images/I/51XKo3FsUyL.jpg", "languages": ["english"], "isbn_10": ["0190906766"], "publish_date": "Dec 18, 2018", "product_group": "Book", "qlt": "used"}
    result = clean_amazon_metadata_for_load(amazon)
    # TODO: implement and test edition number
    assert isinstance(result['publishers'], list)
    assert result['cover'] == 'https://images-na.ssl-images-amazon.com/images/I/51XKo3FsUyL.jpg'
    assert result['authors'][0]['name'] == 'Rachel Carson'
    assert result.get('isbn') is None
    assert result.get('isbn_13') == ['9780190906764']
    assert result.get('isbn_10') == [   '0190906766']
    assert result['identifiers']['amazon'] == ['0190906766']
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
        ['Killers of the Flower Moon: The Osage Murders and the Birth of the FBI',
            'Killers of the Flower Moon',
            'The Osage Murders and the Birth of the FBI'],
        ['Pachinko (National Book Award Finalist)',
            'Pachinko', None],
        ['Trapped in a Video Game (Book 1) (Volume 1)',
            'Trapped in a Video Game', None],
        ["An American Marriage (Oprah's Book Club): A Novel",
            'An American Marriage', 'A Novel'],
        ['A Novel (German Edition)',
            'A Novel', None],
        ['Vietnam Travel Guide 2019: Ho Chi Minh City - First Journey : 10 Tips For an Amazing Trip',
            'Vietnam Travel Guide 2019 : Ho Chi Minh City - First Journey',
            '10 Tips For an Amazing Trip'],
        ['Secrets of Adobe(r) Acrobat(r) 7. 150 Best Practices and Tips (Russian Edition)',
            'Secrets of Adobe Acrobat 7. 150 Best Practices and Tips', None],
        ['Last Days at Hot Slit: The Radical Feminism of Andrea Dworkin (Semiotext(e) / Native Agents)',
            'Last Days at Hot Slit',
            'The Radical Feminism of Andrea Dworkin'],
        ['Bloody Times: The Funeral of Abraham Lincoln and the Manhunt for Jefferson Davis',
            'Bloody Times',
            'The Funeral of Abraham Lincoln and the Manhunt for Jefferson Davis'],
]

@pytest.mark.parametrize('amazon,title,subtitle', amazon_titles)
def test_split_amazon_title(amazon, title, subtitle):
    assert split_amazon_title(amazon) == (title, subtitle)


def test_clean_amazon_metadata_for_load_subtitle():
    amazon = {"publishers": ["Vintage"], "price": "$4.12 (used)", "physical_format": "paperback", "edition": "Reprint", "authors": [{"name": "David Grann"}], "isbn_13": ["9780307742483"], "price_amt": "4.12", "source_records": ["amazon:0307742482"], "title": "Killers of the Flower Moon: The Osage Murders and the Birth of the FBI", "url": "https://www.amazon.com/dp/0307742482/?tag=internetarchi-20", "offer_summary": {"lowest_new": 869, "amazon_offers": 1, "total_new": 57, "lowest_used": 412, "total_collectible": 2, "total_used": 133, "lowest_collectible": 1475}, "number_of_pages": "400", "cover": "https://images-na.ssl-images-amazon.com/images/I/51PP3iTK8DL.jpg", "languages": ["english"], "isbn_10": ["0307742482"], "publish_date": "Apr 03, 2018", "product_group": "Book", "qlt": "used"}
    result = clean_amazon_metadata_for_load(amazon)
    assert result['title'] == 'Killers of the Flower Moon'
    assert result.get('subtitle') == 'The Osage Murders and the Birth of the FBI'
    assert result.get('full_title') == 'Killers of the Flower Moon : The Osage Murders and the Birth of the FBI'
    #TODO: test for, and implement languages

def test_get_betterworldbooks_thirdparty_metadata():
    import urllib2
    content = urllib2.urlopen(url=BWB_URL).read()
    isbn = re.findall('isbn1=\"([0-9]+)\"', content)[0]
    assert isbn    
    data = _get_betterworldbooks_thirdparty_metadata(isbn)
    assert data.get('price_amt')
    bad_data = betterworldbooks_fmt(isbn)
    assert bad_data.get('isbn') == isbn
    assert bad_data.get('price') is None
    assert bad_data.get('price_amt') is None
    assert bad_data.get('qlt') is None

# Test cases to add:
# Multiple authors

