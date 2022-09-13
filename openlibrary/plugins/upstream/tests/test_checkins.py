from openlibrary.plugins.upstream.checkins import check_ins, make_date_string


class TestMakeDateString:
    def setup_method(self):
        self.checkins = check_ins()

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


class TestIsValid:
    def setup_method(self):
        self.checkins = check_ins()
        self.valid_data = {
            'edition_olid': 'OL1234M',
            'event_type': 'START',
            'year': 2000,
            'month': 3,
            'day': 7,
        }

    def test_required_fields(self):
        assert self.checkins.is_valid(self.valid_data) == True

        missing_edition = {
            'event_type': 'START',
            'year': 2000,
            'month': 3,
            'day': 7,
        }
        missing_event_type = {
            'edition_olid': 'OL1234M',
            'year': 2000,
            'month': 3,
            'day': 7,
        }
        missing_year = {
            'edition_olid': 'OL1234M',
            'event_type': 'START',
            'month': 3,
            'day': 7,
        }
        missing_all = {
            'month': 3,
            'day': 7,
        }
        assert self.checkins.is_valid(missing_edition) == False
        assert self.checkins.is_valid(missing_event_type) == False
        assert self.checkins.is_valid(missing_year) == False
        assert self.checkins.is_valid(missing_all) == False

    def test_event_type_values(self):
        assert self.checkins.is_valid(self.valid_data) == True
        unknown_event_type = {
            'edition_olid': 'OL1234M',
            'event_type': 'sail-the-seven-seas',
            'year': 2000,
            'month': 3,
            'day': 7,
        }
        assert self.checkins.is_valid(unknown_event_type) == False
