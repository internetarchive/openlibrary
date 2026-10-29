from scripts.import_itan import map_data, normalize_whitespace, parse_notes, strip_author_role

SAMPLE_1 = {
    "title": "Shadows Of The Continent",
    "authors": [{"name": "Tolulope Taiwo"}],
    "publishers": ["Itan Technologies"],
    "publish_date": "2026",
    "languages": ["eng"],
    "subjects": ["African Literature & Fiction", " Contemporary Fiction", "romance"],
    "source_records": ["itan_technologies:BOO1109"],
    "identifiers": {"itan_technologies": ["BOO1109"]},
    "ebook_access": "borrowable",
    "url": "https://itan.app/bookstore/african-literature-fiction-shadows-of-the-continent-urunna-ikemefuna-boo1109",
    "subtitle": "A Pan-African Romance Suspense Novel",
    "number_of_pages": 189,
    "notes": "Zara Osei never meant to uncover a murder. | Available on Itan Technologies. Ebook: ₦6,800. | Edition: 0",
    "isbn_13": ["0"],
}


def test_normalize_whitespace():
    assert normalize_whitespace("Obinna Godswill  Chinegwu ") == "Obinna Godswill Chinegwu"
    assert normalize_whitespace(" Contemporary Fiction") == "Contemporary Fiction"
    assert normalize_whitespace("Already Clean") == "Already Clean"


def test_strip_author_role():
    assert strip_author_role("Joshua Okoromodeke (Illustrator)") == "Joshua Okoromodeke"
    assert strip_author_role("Okeke  Clement (Translator)") == "Okeke Clement"
    assert strip_author_role("Jane Doe") == "Jane Doe"


def test_parse_notes_drops_pricing_and_placeholder_edition():
    description, edition_name = parse_notes("A gripping novel. | Available on Itan Technologies. Ebook: ₦6,800. | Edition: 0")
    assert description == "A gripping novel."
    assert edition_name is None


def test_parse_notes_keeps_real_edition():
    assert parse_notes("A blurb. | Available on Itan Technologies. Ebook: ₦4,900. | Edition: Second")[1] == "Second"
    assert parse_notes("A blurb. | Available on Itan Technologies. Ebook: ₦4,900. | Edition: Revised Edition")[1] == "Revised Edition"


def test_parse_notes_normalizes_numeric_editions():
    assert parse_notes("A blurb. | Edition: 1")[1] == "First"
    assert parse_notes("A blurb. | Edition: 01")[1] == "First"
    assert parse_notes("A blurb. | Edition: 1st")[1] == "First"
    assert parse_notes("A blurb. | Edition: 2")[1] == "Second"


def test_parse_notes_without_edition_segment():
    description, edition_name = parse_notes("Just a blurb. | Available on Itan Technologies. Ebook: ₦3,500.")
    assert description == "Just a blurb."
    assert edition_name is None


def test_map_data():
    assert map_data(SAMPLE_1) == {
        "title": "Shadows Of The Continent",
        "source_records": ["itan_technologies:BOO1109"],
        "publishers": ["Itan Technologies"],
        "publish_date": "2026",
        "authors": [{"name": "Tolulope Taiwo"}],
        "languages": ["eng"],
        "identifiers": {"itan_technologies": ["BOO1109"]},
        "subtitle": "A Pan-African Romance Suspense Novel",
        "subjects": ["African Literature & Fiction", "Contemporary Fiction", "romance"],
        "description": "Zara Osei never meant to uncover a murder.",
        "number_of_pages": 189,
        "links": [
            {
                "url": "https://itan.app/bookstore/african-literature-fiction-shadows-of-the-continent-urunna-ikemefuna-boo1109",
                "title": "Read on ITAN",
            }
        ],
    }


def test_map_data_drops_placeholder_isbn_and_ebook_access():
    record = map_data(SAMPLE_1)
    assert "isbn_13" not in record
    assert "isbn_13" not in record["identifiers"]
    assert "ebook_access" not in record
    assert "url" not in record


def test_map_data_omits_optional_fields_when_absent():
    record = map_data({**SAMPLE_1, "subtitle": "", "number_of_pages": 0, "subjects": [], "url": None})
    assert "subtitle" not in record
    assert "number_of_pages" not in record
    assert "subjects" not in record
    assert "links" not in record


def test_map_data_normalizes_authors_and_contributions():
    record = map_data(
        {
            **SAMPLE_1,
            "authors": [{"name": "Obinna Godswill  Chinegwu "}],
            "contributions": ["Joshua Okoromodeke (Illustrator)"],
        }
    )
    assert record["authors"] == [{"name": "Obinna Godswill Chinegwu"}]
    assert record["contributions"] == ["Joshua Okoromodeke"]


def test_map_data_dedupes_subjects():
    record = map_data({**SAMPLE_1, "subjects": ["romance", " romance ", "fiction"]})
    assert record["subjects"] == ["romance", "fiction"]


def test_parse_notes_normalizes_spelled_out_editions():
    assert parse_notes("A blurb. | Edition: First Edition")[1] == "First"
    assert parse_notes("A blurb. | Edition: First")[1] == "First"
