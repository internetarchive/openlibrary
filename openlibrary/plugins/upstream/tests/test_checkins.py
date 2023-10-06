from openlibrary.plugins.upstream.checkins import (
    is_valid_date,
    make_date_string,
    patron_check_ins,
)


class TestMakeDateString:
    def test_formatting(self):
        date_str = make_date_string(2000, 12, 22)
        assert date_str == "2000-12-22"

    def test_zero_padding(self):
        date_str = make_date_string(2000, 2, 2)
        split_date = date_str.split('-')
        assert len(split_date) == 3
        # Year has four characters:
        assert len(split_date[0]) == 4
        # Month has two characters:
        assert len(split_date[1]) == 2
        # Day has two characters:
        assert len(split_date[2]) == 2

    def test_partial_dates(self):
        year_resolution = make_date_string(1998, None, None)
        assert year_resolution == "1998"
        month_resolution = make_date_string(1998, 10, None)
        assert month_resolution == "1998-10"
        missing_month = make_date_string(1998, None, 10)
        assert missing_month == "1998"


class TestIsValidDate:
    def test_date_validation(self):
        assert is_valid_date(1999, None, None) is True
        assert is_valid_date(1999, 2, None) is True
        assert is_valid_date(1999, 2, 30) is True

        # Must have a year:
        assert is_valid_date(None, 1, 21) is False
        # Must have a month if there is a day:
        assert is_valid_date(1999, None, 22) is False


class TestValidateData:
    def setup_method(self):
        self.checkins = patron_check_ins()
        self.valid_data = {
            'edition_key': '/books/OL1234M',
            'event_type': 3,
            'year': 2000,
            'month': 3,
            'day': 7,
        }
        self.missing_event = {
            'edition_key': '/books/OL1234M',
            'year': 2000,
            'month': 3,
            'day': 7,
        }
        self.invalid_date = {
            'edition_key': '/books/OL1234M',
            'event_type': 3,
            'month': 3,
            'day': 7,
        }
        self.unknown_event = {
            'edition_key': '/books/OL1234M',
            'event_type': 54321,
            'year': 2000,
            'month': 3,
            'day': 7,
        }

    def test_validate_data(self):
        assert self.checkins.validate_data(self.valid_data) is True
        assert self.checkins.validate_data(self.missing_event) is False
        assert self.checkins.validate_data(self.invalid_date) is False
        assert self.checkins.validate_data(self.unknown_event) is False
