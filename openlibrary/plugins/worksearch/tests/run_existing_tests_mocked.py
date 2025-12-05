import sys
from unittest.mock import MagicMock

# Mock psycopg2 and db before they are imported
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.errors'] = MagicMock()
sys.modules['openlibrary.core.db'] = MagicMock()

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(["openlibrary/plugins/worksearch/tests/test_worksearch.py"]))
