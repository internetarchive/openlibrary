from openlibrary.plugins.worksearch.schemes.authors import AuthorSearchScheme


def test_name_sort_uses_populated_author_sort_field():
    assert AuthorSearchScheme().process_user_sort("name") == "name_str asc"
