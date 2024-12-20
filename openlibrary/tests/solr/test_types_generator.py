import os

from openlibrary.solr.types_generator import generate

root = os.path.dirname(__file__)


def test_up_to_date():
    types_path = os.path.join(root, '..', '..', 'solr', 'solr_types.py')
    assert (
        generate().strip() == open(types_path).read().strip()
    ), """
    This auto-generated file is out-of-date. Run:
    ./openlibrary/solr/types_generator.py > ./openlibrary/solr/solr_types.py
    """
