from openlibrary.core.lists import EditionProcessor

class TestEditionProcessor:
    def test_process_subject(self):
        s = EditionProcessor()
        assert s.process_subject("foo") == "foo"
        assert s.process_subject("foo bar") == "foo_bar"
        assert s.process_subject("Foo Bar") == "foo_bar"
        
    def test_find_work_feeds(self):
        s = EditionProcessor()
        def f(doc):
            return set(s.find_work_seeds(doc))
        
        doc = {
            "key": "/works/OL1M"
        }
        assert f(doc) == set(["/works/OL1M"])

        # test author
        doc = {
            "key": "/works/OL1M",
            "authors": [{
                "author": {"key": "/authors/OL1A"}
            }]
        }
        assert f(doc) == set(["/works/OL1M", "/authors/OL1A"])
        
        # test bad author
        doc = {
            "key": "/works/OL1M",
            "authors": [{
                "type": {"key": "/type/author_role"}
            }]
        }
        assert f(doc) == set(["/works/OL1M"])

        # test subjects
        doc = {
            "key": "/works/OL1M",
            "subjects": ["foo"],
            "subject_places": ["san_francisco"],
            "subject_times": ["18th_century"],
            "subject_people": ["mark_twain"],
        }
        assert f(doc) == set([
            "/works/OL1M", 
            "subject:foo",
            "place:san_francisco",
            "time:18th_century",
            "person:mark_twain",
        ])

    def test_process_edition(self):
        s = EditionProcessor()
        
        # process_edition returns a iterator with each entry containig:
        # (seed, work_key, edition_key, ebook)
        
        def f(edition, works):
            return set(s.process_edition(edition, works))
        
        # edition with no works
        edition = {
            "key": "/books/OL1M"
        }
        assert f(edition, {}) == set([
            ("/books/OL1M", None, "/books/OL1M", False)
        ])
        
        # edition with no works and ebook
        edition = {
            "key": "/books/OL1M",
            "ocaid": "foo"
        }
        assert f(edition, {}) == set([
            ("/books/OL1M", None, "/books/OL1M", True)
        ])
        
        # edition with one work
        edition = {
            "key": "/books/OL1M",
            "works": [{"key": "/works/OL1W"}]
        }
        works = {
            "/works/OL1W": {
                "key": "/works/OL1W",
                "authors": [{
                    "author": {"key": "/authors/OL1A"}
                }],
                "subjects": ["foo"]
            }
        }

        assert f(edition, works) == set([
            ("/books/OL1M", "/works/OL1W", "/books/OL1M", False),
            ("/works/OL1W", "/works/OL1W", "/books/OL1M", False),
            ("/authors/OL1A", "/works/OL1W", "/books/OL1M", False),
            ("subject:foo", "/works/OL1W", "/books/OL1M", False)
        ])
