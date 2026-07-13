import os

from openlibrary.scorecards import generate_scorecard

root = os.path.dirname(__file__)


def test_edition_scorecard_up_to_date():
    yml_path = os.path.join(root, "..", "edition_scorecard.yml")
    py_path = os.path.join(root, "..", "edition_scorecard.py")
    with open(py_path) as f:
        assert generate_scorecard(yml_path).strip() == f.read().strip(), """
    This auto-generated file is out-of-date. Run:
    ./openlibrary/scorecards.py generate openlibrary/edition_scorecard.yml
    """
