import pytest

from ..import_open_textbook_library import map_data


@pytest.mark.parametrize(
    "input_data, expected_output",
    [
        (
            # Test case 1: Basic case with all fields present
            {
                "id": 1238,
                "title": "Healthcare in the  United States: Navigating the Basics of a Complex System",
                "edition_statement": None,
                "volume": None,
                "copyright_year": 2022,
                "ISBN10": None,
                "ISBN13": "9781940771915",
                "license": "Attribution-ShareAlike",
                "language": "eng",
                "description": "This book is a collaborative effort among three faculty members from the Darton College",
                "contributors": [
                    {
                        "id": 5889,
                        "contribution": "Author",
                        "primary": False,
                        "corporate": False,
                        "title": "Dr.",
                        "first_name": "Deanna",
                        "middle_name": "L.",
                        "last_name": "Howe",
                        "location": "Albany, NY",
                    },
                    {
                        "id": 5890,
                        "contribution": "Author",
                        "primary": False,
                        "corporate": False,
                        "title": "Dr.",
                        "first_name": "Andrea",
                        "middle_name": "L.",
                        "last_name": "Dozier",
                        "location": "Albany, NY",
                    },
                    {
                        "id": 5891,
                        "contribution": None,
                        "primary": False,
                        "corporate": False,
                        "title": "Dr.",
                        "first_name": "Sheree",
                        "middle_name": "O.",
                        "last_name": "Dickenson",
                        "location": "Albany, NY",
                    },
                ],
                "subjects": [
                    {
                        "id": 17,
                        "name": "Medicine",
                        "parent_subject_id": None,
                        "call_number": "RA440",
                        "visible_textbooks_count": 74,
                        "url": "https://open.umn.edu/opentextbooks/subjects/medicine",
                    }
                ],
                "publishers": [
                    {
                        "id": 1217,
                        "name": "University of North Georgia Press",
                        "url": "https://ung.edu/university-press/",
                        "year": None,
                        "created_at": "2022-08-25T14:37:55.000Z",
                        "updated_at": "2022-08-25T14:37:55.000Z",
                    }
                ],
            },
            {
                "identifiers": {"open_textbook_library": ["1238"]},
                "source_records": ["open_textbook_library:1238"],
                "title": "Healthcare in the  United States: Navigating the Basics of a Complex System",
                "isbn_13": ["9781940771915"],
                "languages": ["eng"],
                "description": "This book is a collaborative effort among three faculty members from the Darton College",
                "subjects": ["Medicine"],
                "publishers": ["University of North Georgia Press"],
                "publish_date": "2022",
                "authors": [
                    {"name": "Deanna L. Howe"},
                    {"name": "Andrea L. Dozier"},
                ],
                "contributors": [{'role': None, 'name': 'Sheree O. Dickenson'}],
                "lc_classifications": ["RA440"],
            },
        ),
        # Test case 2: Missing some optional fields
        (
            {
                "id": 895,
                "title": "The ELC: An Early Childhood Learning Community at Work",
                "language": "eng",
                "description": "The ELC professional development model was designed to improve the quality of teacher candidates",
                "contributors": [
                    {
                        "id": 5247,
                        "contribution": "Author",
                        "primary": False,
                        "corporate": False,
                        "title": None,
                        "first_name": "Heather",
                        "middle_name": None,
                        "last_name": "Bridge",
                        "location": None,
                        "background_text": "Heather Bridge",
                    },
                    {
                        "id": 5248,
                        "contribution": "Author",
                        "primary": False,
                        "corporate": False,
                        "title": None,
                        "first_name": "Lorraine",
                        "middle_name": None,
                        "last_name": "Melita",
                        "location": None,
                        "background_text": "Lorraine Melita",
                    },
                    {
                        "id": 5249,
                        "contribution": "Author",
                        "primary": False,
                        "corporate": False,
                        "title": None,
                        "first_name": "Patricia",
                        "middle_name": None,
                        "last_name": "Roiger",
                        "location": None,
                        "background_text": "Patricia Roiger",
                    },
                ],
                "subjects": [
                    {
                        "id": 57,
                        "name": "Early Childhood",
                        "parent_subject_id": 5,
                        "call_number": "LB1139.2",
                        "visible_textbooks_count": 11,
                        "url": "https://open.umn.edu/opentextbooks/subjects/early-childhood",
                    }
                ],
                "publishers": [
                    {
                        "id": 874,
                        "name": "Open SUNY",
                        "url": "https://textbooks.opensuny.org",
                        "year": 2020,
                        "created_at": "2020-07-21T23:48:48.000Z",
                        "updated_at": "2020-07-21T23:48:48.000Z",
                    }
                ],
            },
            {
                "identifiers": {"open_textbook_library": ["895"]},
                "source_records": ["open_textbook_library:895"],
                "title": "The ELC: An Early Childhood Learning Community at Work",
                "languages": ["eng"],
                "description": "The ELC professional development model was designed to improve the quality of teacher candidates",
                "subjects": ["Early Childhood"],
                "publishers": ["Open SUNY"],
                "authors": [
                    {"name": "Heather Bridge"},
                    {"name": "Lorraine Melita"},
                    {"name": "Patricia Roiger"},
                ],
                "lc_classifications": ["LB1139.2"],
            },
        ),
        # Test case 3: None values
        (
            {
                'id': 730,
                'title': 'Mythology Unbound: An Online Textbook for Classical Mythology',
                'ISBN10': None,
                'ISBN13': None,
                'language': None,
                'contributors': [
                    {
                        'first_name': 'EVANS',
                        'middle_name': None,
                        'last_name': None,
                        'contribution': None,
                        'primary': True,
                    },
                    {
                        'first_name': 'Eve',
                        'middle_name': None,
                        'last_name': 'Johnson',
                        'contribution': None,
                        'primary': False,
                    },
                ],
            },
            {
                "identifiers": {"open_textbook_library": ["730"]},
                "source_records": ["open_textbook_library:730"],
                "title": "Mythology Unbound: An Online Textbook for Classical Mythology",
                "authors": [{"name": "EVANS"}],
                "contributors": [{'name': 'Eve Johnson', 'role': None}],
            },
        ),
    ],
)
def test_map_data(input_data, expected_output):
    result = map_data(input_data)
    assert result == expected_output
