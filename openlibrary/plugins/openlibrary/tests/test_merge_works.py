from openlibrary.plugins.openlibrary.api import merge_works


def test_concat_and_uniq_arr_field_values_from_dicts():
    dict_one = {
        "authors": [
            {
                "type": {"key": "/type/author_role"},
                "author": {"key": "/authors/OL2699987A"}
            }
        ]
    }
    dict_two = {
        "authors": [
            {
                "author": {"key": "/authors/OL2699987A"},
                "type": {"key": "/type/author_role"}
            }
        ]
    }
    arr = merge_works.uniq_arr_field_values_from_dicts('authors', dict_one, dict_two)
    assert len(arr) == 1
    assert arr[0]['type']['key'] == "/type/author_role"
    assert arr[0]['author']['key'] == "/authors/OL2699987A"

    arr = merge_works.uniq_arr_field_values_from_dicts('subjects', {
        'subjects': ['subject_one', 'subject_two']
    }, {
        'subjects': ['subject_two']
    })
    assert len(arr) == 2
    assert 'subject_one' in arr
    assert 'subject_two' in arr
