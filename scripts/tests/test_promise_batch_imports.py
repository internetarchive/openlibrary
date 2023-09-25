import pytest

from ..promise_batch_imports import format_date, USE_ONLY_YEAR


@pytest.mark.parametrize(
    "date, return_only_year_pattern, expected",
    [
        ("20001020", USE_ONLY_YEAR, "2000-10-20"),
        ("20000101", USE_ONLY_YEAR, "2000"),
        ("20000000", USE_ONLY_YEAR, "2000"),
    ],
)
def test_format_date(date, return_only_year_pattern, expected) -> None:
    assert format_date(date, return_only_year_pattern) == expected
