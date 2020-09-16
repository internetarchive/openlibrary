import sys

import pytest

from openlibrary.core.lists.model import Seed


@pytest.mark.xfail(sys.version_info >= (3, ), reason="does not work on Python 3")
def test_seed_with_string():
    seed = Seed([1, 2, 3], "subject/Politics and government")
    assert seed._list == [1, 2, 3]
    assert seed.value == "subject/Politics and government"
    assert seed.key == "subject/Politics and government"
    assert seed.type == "subject"
    assert seed._solrdata is None


class NotAString(object):
    def __init__(self):
        self.key = "not_a_string.key"


@pytest.mark.xfail(sys.version_info >= (3, ), reason="does not work on Python 3")
def test_seed_with_nonstring():
    seed = Seed((1, 2, 3), NotAString())
    assert seed._list == (1, 2, 3)
    assert isinstance(seed.value, NotAString)
    assert hasattr(seed, "key")
    assert hasattr(seed, "type") is False
    assert isinstance(seed.get_document(), NotAString)
    assert isinstance(seed.document, NotAString)
    seed.value = "New value"
    # assert seed.get_document() == "New value"
    assert isinstance(seed.document, NotAString)
 