import pytest

from openlibrary.plugins.worksearch.schemes.__init__ import (
    SearchScheme
)

@pytest.fixture
def searchScheme():
    return SearchScheme()

def test_process_user_query(searchScheme):
    assert searchScheme.process_user_query('Compilation Group for the "History of Modern China') == 'Compilation Group for the History of Modern China'
    assert searchScheme.process_user_query('"Compilation Group for the History of Modern China"') == '"Compilation Group for the History of Modern China"'
    assert searchScheme.process_user_query('"Compilation Group for the "History of Modern China"') == 'Compilation Group for the History of Modern China'
