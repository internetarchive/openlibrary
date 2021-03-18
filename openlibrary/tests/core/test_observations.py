from openlibrary.core.observations import ObservationValue, _sort_values

def test_sort_values():
    unsorted_list = [
      ObservationValue(1, 'two', 3),
      ObservationValue(2, 'four', 4),
      ObservationValue(3, 'one', None),
      ObservationValue(4, 'three', 1),
      ObservationValue(5, 'five', 2)
    ]

    # sorted values returned given unsorted list
    assert _sort_values(unsorted_list) == ['one', 'two', 'three', 'four', 'five']

    # an empty list is returned if an empty list is passed
    assert _sort_values([]) == []