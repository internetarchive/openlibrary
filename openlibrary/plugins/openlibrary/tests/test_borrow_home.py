from .. import borrow_home

class Test_convert_works_to_editions:
    
    def convert(self, site, works):
        borrow_home.convert_works_to_editions(site, works)
        return works
        
    def test_no_lending_edition(self, mock_site):
        """if there is no lending edition, work should stay the same."""
        work = {
            "key": "/works/OL1W",
            "title": "foo"
        }
        assert self.convert(mock_site, [work]) == [work]
    
    def test_lending_edition(self, mock_site):
        """if there is no lending edition, work should stay the same."""
        mock_site.save({
            "key": "/books/OL1M",
            "ocaid": "foo2010bar",
            "title": "bar",
            "covers": [1234]
        })
        
        work = {
            "key": "/works/OL1W",
            "title": "foo",
            "ia": "foofoo",
            "lending_edition": "OL1M",
            "cover_id": 1111
        }
        assert self.convert(mock_site, [work]) == [{
            "key": "/books/OL1M",
            "title": "bar",
            "lending_edition": "OL1M",
            "ia": "foo2010bar",
            "cover_id": 1234
        }]
    
    def test_edition_with_no_title(self, mock_site):
        """When the editon has no title, work's title should be retained."""
        mock_site.save({
            "key": "/books/OL1M",
            "ocaid": "foofoo"
        })
        work = {
            "key": "/works/OL1W",
            "title": "foo",
            "ia": "foofoo",
            "lending_edition": "OL1M"
        }
        assert self.convert(mock_site, [work]) == [{
            "key": "/books/OL1M",
            "title": "foo",
            "lending_edition": "OL1M",
            "ia": "foofoo",
            "cover_id": None
        }]
        
    def test_edition_with_no_cover(self, mock_site):
        """When the editon has no cover, work's cover should *not* be retained."""
        mock_site.save({
            "key": "/books/OL1M",
            "ocaid": "foofoo"
        })
        work = {
            "key": "/works/OL1W",
            "title": "foo",
            "ia": "foofoo",
            "lending_edition": "OL1M",
            "cover_id": 1234
        }
        assert self.convert(mock_site, [work]) == [{
            "key": "/books/OL1M",
            "title": "foo",
            "lending_edition": "OL1M",
            "ia": "foofoo",
            "cover_id": None
        }]
        
        