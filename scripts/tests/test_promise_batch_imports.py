import pytest

from ..promise_batch_imports import format_date


@pytest.mark.parametrize(
    ("date", "only_year", "expected"),
    [
        ("20001020", False, "2000-10-20"),
        ("20000101", True, "2000"),
        ("20000000", True, "2000"),
    ],
)
def test_format_date(date, only_year, expected) -> None:
    assert format_date(date=date, only_year=only_year) == expected
