"""
Create a edition dict that can be passed to catalog.add_book.load()

This class encapsulates the logic of creating edition dicts.

You can use add(key) to add a new key to the edition dict. This class
will take care of whether it should be a string or a list. For example,
you can use add('subject') to add an entry to the 'subjects' list.

This class also takes care of creating complex types, such as authors.
For example, you can add an author using add('author', 'Mark Twain') and
we will create {'personal_name': ..., 'name': ..., 'entity_type': 'person'}
which is stored as a list of authors in the edition dict.

A sample dict looks like one of these:
{
    "edition_name": "3rd ed.",
    "pagination": "xii, 444 p.",
    "title": "A course of pure mathematics",
    "publishers": ["At the University Press"],
    "number_of_pages": 444,
    "languages": ["eng"],
    "publish_date": "1921",
    "location": ["GLAD"],
    "authors": [
        {
            "birth_date": "1877",
            "personal_name": "Hardy, G. H.",
            "death_date": "1947",
            "name": "Hardy, G. H.",
            "entity_type": "person",
        }
    ],
    "by_statement": "by G.H. Hardy",
    "publish_places": ["Cambridge"],
    "publish_country": "enk",
}
{
    "publishers": ["Ace Books"],
    "pagination": "271 p. ;",
    "title": "Neuromancer",
    "lccn": ["91174394"],
    "notes": "Hugo award book, 1985; Nebula award ; Philip K. Dick award",
    "number_of_pages": 271,
    "isbn_13": ["9780441569595"],
    "languages": ["eng"],
    "dewey_decimal_class": ["813/.54"],
    "lc_classifications": ["PS3557.I2264 N48 1984", "PR9199.3.G53 N49 1984"],
    "publish_date": "1984",
    "publish_country": "nyu",
    "authors": [
        {
            "birth_date": "1948",
            "personal_name": "Gibson, William",
            "name": "Gibson, William",
            "entity_type": "person",
        }
    ],
    "by_statement": "William Gibson",
    "oclc_numbers": ["24379880"],
    "publish_places": ["New York"],
    "isbn_10": ["0441569595"],
}
{
    "publishers": ["Grosset & Dunlap"],
    "pagination": "156 p.",
    "title": "Great trains of all time",
    "lccn": ["62051844"],
    "number_of_pages": 156,
    "languages": ["eng"],
    "dewey_decimal_class": ["625.2"],
    "lc_classifications": ["TF147 .H8"],
    "publish_date": "1962",
    "publish_country": "nyu",
    "authors": [
        {
            "birth_date": "1894",
            "personal_name": "Hubbard, Freeman H.",
            "name": "Hubbard, Freeman H.",
            "entity_type": "person",
        }
    ],
    "by_statement": "Illustrated by Herb Mott",
    "oclc_numbers": ["1413013"],
    "publish_places": ["New York"],
}
"""

from openlibrary.plugins.importapi.import_validator import import_validator


class import_edition_builder:
    def add_string(self, key, val):
        self.edition_dict[key] = val

    def add_list(self, key, val):
        if key in self.edition_dict:
            self.edition_dict[key].append(val)
        else:
            self.edition_dict[key] = [val]

    def add_author(self, key, val):
        # We don't know birth_date or death_date.
        # Should name and personal_name be the same value?
        author_dict = {'personal_name': val, 'name': val, 'entity_type': 'person'}
        self.add_list('authors', author_dict)

    def add_illustrator(self, key, val):
        self.add_list('contributions', val + ' (Illustrator)')

    def __init__(self, init_dict=None):
        init_dict = init_dict or {}
        self.edition_dict = init_dict.copy()
        self._validate()

        self.type_dict = {
            'title': ['title', self.add_string],
            'author': ['authors', self.add_author],
            'publisher': ['publishers', self.add_list],
            'publish_place': ['publish_places', self.add_list],
            'publish_date': ['publish_date', self.add_string],
            'pagination': ['pagination', self.add_string],
            'subject': ['subjects', self.add_list],
            'language': ['languages', self.add_list],
            'description': ['description', self.add_string],
            'lccn': ['lccn', self.add_list],
            'oclc_number': ['oclc_numbers', self.add_list],
            'isbn_10': ['isbn_10', self.add_list],
            'isbn_13': ['isbn_13', self.add_list],
            'ocaid': ['ocaid', self.add_string],
            'illustrator': ['contributions', self.add_illustrator],
            'source_record': ['source_records', self.add_list],
            'dewey_decimal_class': ['dewey_decimal_class', self.add_list],
            'lc_classification': ['lc_classifications', self.add_list],
        }

    def _validate(self):
        import_validator().validate(self.edition_dict)

    def get_dict(self):
        return self.edition_dict

    def add(self, key, val, restrict_keys=True):
        if restrict_keys and key not in self.type_dict:
            print('import_edition_builder invalid key: ' + key)
            return

        if key in self.type_dict:
            new_key = self.type_dict[key][0]
            add_func = self.type_dict[key][1]
            add_func(new_key, val)
        else:
            self.add_string(key, val)
