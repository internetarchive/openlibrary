from openlibrary.core.lists.engine import SeedEngine
from openlibrary.core.mocksite import MockSite

class TestEditionProcessor:
    def test_process_subject(self):
        s = SeedEngine(None)
        assert s._subject_key("foo") == "foo"
        assert s._subject_key("foo bar") == "foo_bar"
        assert s._subject_key("Foo Bar") == "foo_bar"

    def test_process_edition(self):
        site = MockSite()
        s = SeedEngine(site)
        
        # process_edition returns a iterator with each entry containig:
        # (seed, work_key, edition_key, ebook)
        
        def f(edition):
            result = sorted(s.process_edition(edition))
            print result
            return result
            
        # edition with no works
        edition = {
            "key": "/books/OL1M"
        }
        assert f(edition) == [
            {"key": "/books/OL1M"},
        ]
        
        # edition with no works and ebook
        edition = {
            "key": "/books/OL1M",
            "ocaid": "foo"
        }
        assert f(edition) == [
            {"key": "/books/OL1M"},
        ]
        
        # edition with one work
        edition = {
            "key": "/books/OL1M",
            "works": [{"key": "/works/OL1W"}]
        }
        
        site.save({
            "key": "/works/OL1W",
            "authors": [{
                "author": {"key": "/authors/OL1A"}
            }],
            "subjects": ["foo"]
        })

        assert f(edition) == [
            {"key": "/authors/OL1A"},
            {"key": "/books/OL1M"},
            {"key": "/works/OL1W"},
            "subject:foo"
        ]
