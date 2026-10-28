from openlibrary.catalog import get_location_and_publisher

def test_empty_publisher():
    # Test with an empty publisher
    publisher, locations = get_location_and_publisher("Place of publication not identified")
    assert publisher == [], "Expected an empty publisher, got: " + str(publisher)
    assert locations == [], "Expected an empty list of locations, got: " + str(locations)
