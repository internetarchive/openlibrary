import unittest
from datetime import datetime
from unittest.mock import MagicMock

from openlibrary.admin import numbers


class TestAdminNumbers(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.start = datetime(2023, 1, 1)
        self.end = datetime(2023, 1, 2)
        self.kwargs = {'thingdb': self.mock_db, 'start': self.start, 'end': self.end}

    def test_active_logins_query(self):
        # Setup mock return
        self.mock_db.query.return_value = [MagicMock(count=100)]

        # Call function
        result = numbers.admin_range__active_logins(**self.kwargs)

        # Assertions
        self.assertEqual(result, 100)
        # Verify query structure
        query_arg = self.mock_db.query.call_args[0][0]
        self.assertIn("store_index", query_arg)
        self.assertIn("last_login", query_arg)
        self.assertIn("count(distinct store_id)", query_arg.lower())

    def test_returning_logins_query(self):
        self.mock_db.query.return_value = [MagicMock(count=50)]

        result = numbers.admin_range__returning_logins(**self.kwargs)

        self.assertEqual(result, 50)
        query_arg = self.mock_db.query.call_args[0][0]
        # Verify we are joining store_index twice
        self.assertIn("store_index s_login", query_arg)
        self.assertIn("store_index s_created", query_arg)
        # Verify conditions
        self.assertIn("last_login", query_arg)
        self.assertIn("created_on", query_arg)
        self.assertIn("value < $month_start", query_arg)

    def test_unique_editors_query(self):
        self.mock_db.query.return_value = [MagicMock(count=25)]

        result = numbers.admin_range__unique_editors(**self.kwargs)

        self.assertEqual(result, 25)
        query_arg = self.mock_db.query.call_args[0][0]
        self.assertIn("transaction", query_arg.lower())
        self.assertIn("count(distinct t.author_id)", query_arg.lower())
        self.assertIn("account", query_arg.lower())  # checking bot exclusion subquery

    def test_edits_by_type_query(self):
        # Mock returning list of objects with type_key and count attributes
        # Since the code does "r.type_key.split('/')[-1]", we need valid keys
        mock_row1 = MagicMock()
        mock_row1.type_key = "/type/work"
        mock_row1.count = 10

        mock_row2 = MagicMock()
        mock_row2.type_key = "/type/edition"
        mock_row2.count = 20

        self.mock_db.query.return_value = [mock_row1, mock_row2]

        result = numbers.admin_range__edits_by_type(**self.kwargs)

        self.assertEqual(result, {"work": 10, "edition": 20})

        query_arg = self.mock_db.query.call_args[0][0]
        self.assertIn("transaction t", query_arg)
        self.assertIn("version v", query_arg)
        self.assertIn("thing type_thing", query_arg)
        self.assertIn("group by type_thing.key", query_arg.lower())


if __name__ == '__main__':
    unittest.main()
