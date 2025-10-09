from collections.abc import Sequence

import pytest
import web

from openlibrary.catalog.add_book.tests.conftest import add_languages  # noqa: F401
from openlibrary.mocks.mock_infobase import MockSite

from .. import utils


def test_url_quote():
    assert utils.url_quote('https://foo bar') == 'https%3A%2F%2Ffoo+bar'
    assert utils.url_quote('abc') == 'abc'
    assert utils.url_quote('Kabitā') == 'Kabit%C4%81'
    assert utils.url_quote('Kabit\u0101') == 'Kabit%C4%81'


def test_urlencode():
    f = utils.urlencode
    assert f({}) == '', 'empty dict'
    assert f([]) == '', 'empty list'
    assert f({'q': 'hello'}) == 'q=hello', 'basic dict'
    assert f({'q': ''}) == 'q=', 'empty param value'
    assert f({'q': None}) == 'q=None', 'None param value'
    assert f([('q', 'hello')]) == 'q=hello', 'basic list'
    assert f([('x', '3'), ('x', '5')]) == 'x=3&x=5', 'list with multi keys'
    assert f({'q': 'a b c'}) == 'q=a+b+c', 'handles spaces'
    assert f({'q': 'a$$'}) == 'q=a%24%24', 'handles special ascii chars'
    assert f({'q': 'héé'}) == 'q=h%C3%A9%C3%A9'
    assert f({'q': 'héé'}) == 'q=h%C3%A9%C3%A9', 'handles unicode without the u?'
    assert f({'q': 1}) == 'q=1', 'numbers'
    assert f({'q': ['test']}) == 'q=%5B%27test%27%5D', 'list'
    assert f({'q': 'αβγ'}) == 'q=%CE%B1%CE%B2%CE%B3', 'unicode without the u'
    assert f({'q': 'αβγ'.encode()}) == 'q=%CE%B1%CE%B2%CE%B3', 'uf8 encoded unicode'
    assert f({'q': 'αβγ'}) == 'q=%CE%B1%CE%B2%CE%B3', 'unicode'


def test_entity_decode():
    assert utils.entity_decode('&gt;foo') == '>foo'
    assert utils.entity_decode('<h1>') == '<h1>'


def test_set_share_links():
    class TestContext:
        def __init__(self):
            self.share_links = None

    test_context = TestContext()
    utils.set_share_links(url='https://foo.com', title="bar", view_context=test_context)
    assert test_context.share_links == [
        {
            'text': 'Facebook',
            'url': 'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Ffoo.com',
        },
        {
            'text': 'Twitter',
            'url': 'https://twitter.com/intent/tweet?url=https%3A%2F%2Ffoo.com&via=openlibrary&text=Check+this+out%3A+bar',
        },
        {
            'text': 'Pinterest',
            'url': 'https://pinterest.com/pin/create/link/?url=https%3A%2F%2Ffoo.com&description=Check+this+out%3A+bar',
        },
    ]


def test_set_share_links_unicode():
    # example work that has a unicode title: https://openlibrary.org/works/OL14930766W/Kabit%C4%81
    class TestContext:
        def __init__(self):
            self.share_links = None

    test_context = TestContext()
    utils.set_share_links(
        url='https://foo.\xe9', title='b\u0101', view_context=test_context
    )
    assert test_context.share_links == [
        {
            'text': 'Facebook',
            'url': 'https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Ffoo.%C3%A9',
        },
        {
            'text': 'Twitter',
            'url': 'https://twitter.com/intent/tweet?url=https%3A%2F%2Ffoo.%C3%A9&via=openlibrary&text=Check+this+out%3A+b%C4%81',
        },
        {
            'text': 'Pinterest',
            'url': 'https://pinterest.com/pin/create/link/?url=https%3A%2F%2Ffoo.%C3%A9&description=Check+this+out%3A+b%C4%81',
        },
    ]


def test_item_image():
    assert utils.item_image('//foo') == 'https://foo'
    assert utils.item_image(None, 'bar') == 'bar'
    assert utils.item_image(None) is None


def test_canonical_url():
    web.ctx.path = '/authors/Ayn_Rand'
    web.ctx.query = ''
    web.ctx.host = 'www.openlibrary.org'
    request = utils.Request()

    url = 'https://www.openlibrary.org/authors/Ayn_Rand'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand'
    assert request.canonical_url == url

    web.ctx.query = '?page=2'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?page=2&sort=newest'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest&page=2'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest&page=2&mode=e'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2'
    assert request.canonical_url == url

    web.ctx.query = '?sort=newest&page=2&mode=e&test=query'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand?page=2&test=query'
    assert request.canonical_url == url

    web.ctx.query = '?sort=new&mode=2'
    url = 'https://www.openlibrary.org/authors/Ayn_Rand'
    assert request.canonical_url == url


def test_get_coverstore_url(monkeypatch):
    from infogami import config  # noqa: PLC0415

    monkeypatch.delattr(config, "coverstore_url", raising=False)
    assert utils.get_coverstore_url() == "https://covers.openlibrary.org"

    monkeypatch.setattr(config, "coverstore_url", "https://0.0.0.0:80", raising=False)
    assert utils.get_coverstore_url() == "https://0.0.0.0:80"

    # make sure trailing / is always stripped
    monkeypatch.setattr(config, "coverstore_url", "https://0.0.0.0:80/", raising=False)
    assert utils.get_coverstore_url() == "https://0.0.0.0:80"


def test_reformat_html():
    f = utils.reformat_html

    input_string = '<p>This sentence has 32 characters.</p>'
    assert f(input_string, 10) == 'This sente...'
    assert f(input_string) == 'This sentence has 32 characters.'
    assert f(input_string, 5000) == 'This sentence has 32 characters.'

    multi_line_string = """<p>This sentence has 32 characters.</p>
                           <p>This new sentence has 36 characters.</p>"""
    assert (
        f(multi_line_string) == 'This sentence has 32 '
        'characters.<br>This new sentence has 36 characters.'
    )
    assert f(multi_line_string, 34) == 'This sentence has 32 characters.<br>T...'

    assert f("<script>alert('hello')</script>", 34) == "alert(&#39;hello&#39;)"
    assert f("&lt;script&gt;") == "&lt;script&gt;"


def test_strip_accents():
    f = utils.strip_accents
    assert f('Plain ASCII text') == 'Plain ASCII text'
    assert f('Des idées napoléoniennes') == 'Des idees napoleoniennes'
    # It only modifies Unicode Nonspacing Mark characters:
    assert f('Bokmål : Standard Østnorsk') == 'Bokmal : Standard Østnorsk'


def test_get_abbrev_from_full_lang_name(
    mock_site: MockSite, monkeypatch, add_languages  # noqa F811
) -> None:
    utils.get_languages.cache_clear()

    monkeypatch.setattr(web, "ctx", web.storage())
    web.ctx.site = mock_site

    web.ctx.site.save(
        {
            "code": "eng",
            "key": "/languages/eng",
            "name": "English",
            "type": {"key": "/type/language"},
            "name_translated": {
                "tg": ["ингилисӣ"],
                "en": ["English"],
                "ay": ["Inlish aru"],
                "pnb": ["انگریزی"],
                "na": ["Dorerin Ingerand"],
            },
        }
    )

    web.ctx.site.save(
        {
            "code": "fre",
            "key": "/languages/fre",
            "name": "French",
            "type": {"key": "/type/language"},
            "name_translated": {
                "ay": ["Inlish aru"],
                "fr": ["anglais"],
                "es": ["spanish"],
            },
        }
    )

    web.ctx.site.save(
        {
            "code": "spa",
            "key": "/languages/spa",
            "name": "Spanish",
            "type": {"key": "/type/language"},
        }
    )

    web.ctx.site.save(
        {
            "code": "por",
            "key": "/languages/por",
            "name": "Portuguese",
            "type": {"key": "/type/language"},
            "name_translated": {
                "en": ["Portuguese", "Portuguese Brazilian"],
            },
        }
    )

    assert utils.get_abbrev_from_full_lang_name("EnGlish") == "eng"
    assert utils.get_abbrev_from_full_lang_name("Dorerin Ingerand") == "eng"
    assert utils.get_abbrev_from_full_lang_name("ингилисӣ") == "eng"
    assert utils.get_abbrev_from_full_lang_name("ингилиси") == "eng"
    assert utils.get_abbrev_from_full_lang_name("Anglais") == "fre"
    assert utils.get_abbrev_from_full_lang_name("Portuguese Brazilian") == "por"

    # See openlibrary/catalog/add_book/tests/conftest.py for imported languages.
    with pytest.raises(utils.LanguageMultipleMatchError):
        utils.get_abbrev_from_full_lang_name("frisian")

    with pytest.raises(utils.LanguageMultipleMatchError):
        utils.get_abbrev_from_full_lang_name("inlish aru")

    with pytest.raises(utils.LanguageMultipleMatchError):
        utils.get_abbrev_from_full_lang_name("Spanish")

    with pytest.raises(utils.LanguageNoMatchError):
        utils.get_abbrev_from_full_lang_name("Missing or non-existent language")


def test_get_colon_only_loc_pub() -> None:
    # This is intended as a helper function, and its caller,
    # get_location_and_publisher(), replaces certain characters,
    # including "[" and "]".
    test_cases = [
        ("", ("", "")),
        ("New York : Random House", ("New York", "Random House")),
        ("[New York] : [Random House]", ("[New York]", "[Random House]")),
        ("Random House,", ("", "Random House")),
    ]

    for tc, expected in test_cases:
        result = utils.get_colon_only_loc_pub(tc)
        assert result == expected, f"For {tc}, expected {expected}, but got {result}"


def test_get_location_and_publisher() -> None:
    # Empty string
    assert utils.get_location_and_publisher("") == ([], [])

    # Test simple case of "City : Publisher".
    loc_pub = "Sŏul T'ŭkpyŏlsi : [Kimyŏngsa]"
    assert utils.get_location_and_publisher(loc_pub) == (
        ["Sŏul T'ŭkpyŏlsi"],
        ["Kimyŏngsa"],
    )

    # Test multiple locations and one publisher.
    loc_pub = "Londres ; [New York] ; Paris : Berlitz Publishing"
    assert utils.get_location_and_publisher(loc_pub) == (
        ["Londres", "New York", "Paris"],
        ["Berlitz Publishing"],
    )

    # Test two locations and two corresponding publishers.
    loc_pub = "Paris : Pearson ; San Jose (Calif.) : Adobe"
    assert utils.get_location_and_publisher(loc_pub) == (
        ["Paris", "San Jose (Calif.)"],
        ["Pearson", "Adobe"],
    )

    # Test location not identified.
    loc_pub = "[Place of publication not identified] : Pearson"
    assert utils.get_location_and_publisher(loc_pub) == ([], ["Pearson"])

    # "Pattern" breaker insofar as it has two colons separators in a row.
    loc_pub = "London : Wise Publications ; Bury St. Edmunds, Suffolk : Exclusive Distributors : Music Sales Limited"
    assert utils.get_location_and_publisher(loc_pub) == (
        ["London"],
        ["Wise Publications"],
    )

    # Bad input where Python thinks the IA metadata is a Python list
    loc_pub = [  # type: ignore[assignment]
        'Charleston, SC : Monkeypaw Press, LLC',
        'Charleston, SC : [manufactured by CreateSpace]',
    ]
    assert utils.get_location_and_publisher(loc_pub) == ([], [])

    # Separating a not identified place with a comma
    loc_pub = "[Place of publication not identified], BARBOUR PUB INC"
    assert utils.get_location_and_publisher(loc_pub) == ([], ["BARBOUR PUB INC"])


@pytest.mark.parametrize(
    ("name", "seq", "locale", "expected"),
    [
        ("English", ["apples", "oranges", "pears"], "en", "apples, oranges, and pears"),
        ("Chinese", ["apples", "oranges", "pears"], "zh", "apples、oranges和pears"),
        (
            "non existent locale",
            ["apples", "oranges", "pears"],
            "nope",
            "apples, oranges, and pears",
        ),
    ],
)
def test_commify_list(
    name: str, seq: Sequence[str], locale: str, expected: str
) -> None:
    web.ctx.lang = locale
    got = utils.commify_list(seq)
    assert got == expected
