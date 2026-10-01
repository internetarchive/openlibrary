import pytest

from openlibrary.utils.async_utils import gallop_back


def _before(boundary: int):
    """A predicate true up to and including `boundary`, recording every probe."""
    probes: list[int] = []

    async def is_before(x: int) -> bool:
        probes.append(x)
        return x <= boundary

    return is_before, probes


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", [999_999, 990_000, 500_000, 12_345, 1])
async def test_gallop_back_lands_within_tolerance_below_the_boundary(boundary):
    is_before, _ = _before(boundary)
    found = await gallop_back(1_000_000, is_before, lowest=1, initial_step=100, tolerance=100)
    assert boundary - 100 <= found <= boundary


@pytest.mark.asyncio
async def test_gallop_back_is_exact_at_tolerance_one():
    is_before, _ = _before(777)
    assert await gallop_back(1_000, is_before) == 777


@pytest.mark.asyncio
async def test_gallop_back_returns_lowest_when_nothing_is_before():
    is_before, probes = _before(-1)
    assert await gallop_back(1_000, is_before, lowest=1) == 1
    assert min(probes) == 1


@pytest.mark.asyncio
async def test_gallop_back_never_probes_start_or_below_lowest():
    is_before, probes = _before(40)
    await gallop_back(1_000, is_before, lowest=5)
    assert 1_000 not in probes
    assert min(probes) >= 5


@pytest.mark.asyncio
async def test_gallop_back_probes_scale_with_distance_not_range():
    """The point of galloping over bisecting: a boundary near `start` is found
    in about the same number of probes whatever lies below it."""
    near, near_probes = _before(10**12 - 5_000)
    await gallop_back(10**12, near, lowest=1)
    small, small_probes = _before(10**6 - 5_000)
    await gallop_back(10**6, small, lowest=1)
    assert len(near_probes) == len(small_probes)
    assert min(near_probes) >= 10**12 - 2 * 5_000
