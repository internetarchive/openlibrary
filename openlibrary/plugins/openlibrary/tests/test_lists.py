from openlibrary.plugins.openlibrary import lists

def test_process_seeds():
    process_seeds = lists.lists_json().process_seeds
    def f(s):
        return process_seeds([s])[0]
    
    assert f("/books/OL1M") == {"key": "/books/OL1M"}
    assert f({"key": "/books/OL1M"}) == {"key": "/books/OL1M"}
    assert f("/subjects/love") == "subject:love"
    assert f("subject:love") == "subject:love"
    