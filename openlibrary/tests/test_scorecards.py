import os
from dataclasses import dataclass

from openlibrary.scorecards import ScorecardCheck, ScorecardSection, generate_scorecard


@dataclass
class SectionA(ScorecardSection):
    passing_check = ScorecardCheck(name="passing_check", score=10, description="Passing", details="Passing details")
    failing_check = ScorecardCheck(name="failing_check", score=5, description="Failing", details="Failing details")


root = os.path.dirname(__file__)


def test_edition_scorecard_up_to_date():
    yml_path = os.path.join(root, "..", "edition_scorecard.yml")
    py_path = os.path.join(root, "..", "edition_scorecard.py")
    with open(py_path) as f:
        assert generate_scorecard(yml_path).strip() == f.read().strip(), """
    This auto-generated file is out-of-date. Run:
    ./openlibrary/scorecards.py generate openlibrary/edition_scorecard.yml
    """


def test_scorecard_section_to_dict():
    section = SectionA(name="Section A")
    section.set_check(SectionA.passing_check, True)

    assert section.to_dict() == {
        "name": "Section A",
        "score": 10,
        "maxScore": 15,
        "checks": [
            {"description": "Passing", "details": "Passing details", "score": 10, "passing": True},
            {"description": "Failing", "details": "Failing details", "score": 5, "passing": False},
        ],
    }
