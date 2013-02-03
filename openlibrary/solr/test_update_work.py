from update_work import build_data

author_counter = 0
edition_counter = 0
work_counter = 0

def make_author(**kw):
    global author_counter
    author_counter += 1
    kw.setdefault("key", "/authors/OL%dA" % author_counter)
    kw.setdefault("type", {"key": "/type/author"})
    kw.setdefault("name", "Foo")
    return kw

def make_edition(**kw):
    global edition_counter
    edition_counter += 1
    kw.setdefault("key", "/books/OL%dM" % edition_counter)
    kw.setdefault("type", {"key": "/type/edition"})
    kw.setdefault("title", "Foo")
    return kw

def make_work(**kw):
    global work_counter
    work_counter += 1
    kw.setdefault("key", "/works/OL%dW" % work_counter)
    kw.setdefault("type", {"key": "/type/work"})
    kw.setdefault("title", "Foo")
    return kw

class Test_build_data:

    def strip_empty_lists(self, d):
        """strips empty lists from a dict"""
        def emptylist(x):
            return isinstance(x, list) and len(x) == 0

        return dict((k, v) for k, v  in d.items() if not emptylist(v))

    def match_dicts(self, d, expected):
        """Returns True if d has all the keys in expected and all those values are equal.
        """
        return all(k in d for k in expected) and all(d[k] == expected[k] for k in expected)

    def test_simple(self):
        work = {
            "key": "/works/OL1M",
            "type": {"key": "/type/work"},
            "title": "Foo"
        }

        d = build_data(work)
        assert self.match_dicts(self.strip_empty_lists(d), {
            "key": "OL1M",
            "title": "Foo",
            "has_fulltext": False,
            "edition_count": 0,
        })

    def test_edition_count(self):
        work = make_work()

        d = build_data(work)
        assert d['edition_count'] == 0

        work['editions'] = [make_edition()]
        d = build_data(work)
        assert d['edition_count'] == 1
    
        work['editions'] = [make_edition(), make_edition()]
        d = build_data(work)
        assert d['edition_count'] == 2

    def test_edition_key(self):
        work = make_work(editions=[
            make_edition(key="/books/OL1M"),
            make_edition(key="/books/OL2M"),
            make_edition(key="/books/OL3M")])

        d = build_data(work)
        assert d['edition_key'] == ["OL1M", "OL2M", "OL3M"]

    def test_publish_year(self):
        work = make_work(editions=[
                    make_edition(publish_date="2000"),
                    make_edition(publish_date="Another 2000"),

                    ## Doesn't seems to be handling this case
                    #make_edition(publish_date="2001-01-02"),

                    make_edition(publish_date="Jan 2002"),
                    make_edition(publish_date="Bad date 12")])

        d = build_data(work)
        assert set(d['publish_year']) == set(["2000", "2002"])
        assert d["first_publish_year"] == 2000

    def test_isbns(self):
        work = make_work(editions=[
                    make_edition(isbn_10=["123456789X"])])
        d = build_data(work)
        assert d['isbn'] == ['123456789X', '9781234567897']

        work = make_work(editions=[
                    make_edition(isbn_10=["9781234567897"])])
        d = build_data(work)
        assert d['isbn'] == ['123456789X', '9781234567897']

    def test_other_identifiers(self):
        work = make_work(editions=[
                    make_edition(oclc_numbers=["123"], lccn=["lccn-1", "lccn-2"]),
                    make_edition(oclc_numbers=["234"], lccn=["lccn-2", "lccn-3"]),
        ])
        d = build_data(work)
        assert sorted(d['oclc']) == ['123', '234']
        assert sorted(d['lccn']) == ['lccn-1', 'lccn-2', 'lccn-3']
        
    def test_identifiers(self):
        work = make_work(editions=[
                    make_edition(identifiers={"librarything": ["lt-1"]}),
                    make_edition(identifiers={"librarything": ["lt-2"]})
        ])
        d = build_data(work)
        assert sorted(d['id_librarything']) == ['lt-1', 'lt-2']
        assert 'overdrive_s' not in d

        e1 = make_edition(identifiers={"overdrive": ["o-1"]})
        e2 = make_edition(identifiers={"overdrive": ["o-2"]})
        work = make_work(editions=[e1, e2])
        d = build_data(work)
        assert sorted(d['id_overdrive']) == ['o-1', 'o-2']
        assert sorted(d['overdrive_s'].split(";")) == ['o-1', 'o-2']

    def test_ia_boxid(self):
        e = make_edition()
        w = make_work(editions=[e])
        d = build_data(w)
        assert 'ia_box_id' not in d

        e = make_edition(ia_box_id='foo')
        w = make_work(editions=[e])
        d = build_data(w)
        assert 'ia_box_id' in d
        assert d['ia_box_id'] == ['foo']

    def test_with_one_lending_edition(self):
        e = make_edition(key="/books/OL1M", ocaid='foo00bar', _ia_meta={"collection":['lendinglibrary', 'americana']})
        w = make_work(editions=[e])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert 'printdisabled_s' not in d
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo00bar']
        assert d['ia_collection_s'] == "lendinglibrary;americana"
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    def test_with_two_lending_editions(self):
        e1 = make_edition(key="/books/OL1M", ocaid='foo01bar', _ia_meta={"collection":['lendinglibrary', 'americana']})
        e2 = make_edition(key="/books/OL2M", ocaid='foo02bar', _ia_meta={"collection":['lendinglibrary', 'internetarchivebooks']})
        w = make_work(editions=[e1, e2])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert 'printdisabled_s' not in d
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo01bar', 'foo02bar']
        assert d['ia_collection_s'] == "lendinglibrary;americana;internetarchivebooks"
        assert d['edition_count'] == 2
        assert d['ebook_count_i'] == 2

    def test_with_one_inlibrary_edition(self):
        e = make_edition(key="/books/OL1M", ocaid='foo00bar', _ia_meta={"collection":['printdisabled', 'inlibrary']})
        w = make_work(editions=[e])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert d['printdisabled_s'] == 'OL1M'
        assert d['lending_edition_s'] == 'OL1M'
        assert d['ia'] == ['foo00bar']
        assert d['ia_collection_s'] == "printdisabled;inlibrary"
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    def test_with_one_printdisabled_edition(self):
        e = make_edition(key="/books/OL1M", ocaid='foo00bar', _ia_meta={"collection":['printdisabled', 'americana']})
        w = make_work(editions=[e])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == False
        assert d['printdisabled_s'] == 'OL1M'
        assert 'lending_edition_s' not in d
        assert d['ia'] == ['foo00bar']
        assert d['ia_collection_s'] == "printdisabled;americana"
        assert d['edition_count'] == 1
        assert d['ebook_count_i'] == 1

    def test_with_multliple_editions(self):
        e1 = make_edition(key="/books/OL1M")
        e2 = make_edition(key="/books/OL2M", ocaid='foo00bar', _ia_meta={"collection":['americana']})
        e3 = make_edition(key="/books/OL3M", ocaid='foo01bar', _ia_meta={"collection":['lendinglibrary', 'americana']})
        e4 = make_edition(key="/books/OL4M", ocaid='foo02bar', _ia_meta={"collection":['printdisabled', 'inlibrary']})
        w = make_work(editions=[e1, e2, e3, e4])
        d = build_data(w)
        assert d['has_fulltext'] == True
        assert d['public_scan_b'] == True
        assert d['printdisabled_s'] == 'OL4M'
        assert d['lending_edition_s'] == 'OL3M'
        assert d['ia'] == ['foo00bar', 'foo01bar', 'foo02bar']
        assert sorted(d['ia_collection_s'].split(";")) == ["americana", "inlibrary", "lendinglibrary", "printdisabled"]

        assert d['edition_count'] == 4
        assert d['ebook_count_i'] == 3

    def test_subjects(self):
        w = make_work(subjects=["a", "b c"])
        d = build_data(w)

        assert d['subject'] == ['a', "b c"]
        assert d['subject_facet'] == ['a', "b c"]
        assert d['subject_key'] == ['a', "b_c"]

        assert "people" not in d
        assert "place" not in d
        assert "time" not in d

        w = make_work(
                subjects=["a", "b c"], 
                subject_places=["a", "b c"],
                subject_people=["a", "b c"],
                subject_times=["a", "b c"])
        d = build_data(w)

        for k in ['subject', 'person', 'place', 'time']:
            assert d[k] == ['a', "b c"]
            assert d[k + '_facet'] == ['a', "b c"]
            assert d[k + '_key'] == ['a', "b_c"]

    def test_language(self):
        pass

    def test_author_info(self):
        w = make_work(authors=[
                {"author": make_author(key="/authors/OL1A", name="Author One", alternate_names=["Author 1"])},
                {"author": make_author(key="/authors/OL2A", name="Author Two")}
            ])
        d = build_data(w)
        assert d['author_name'] == ["Author One", "Author Two"]
        assert d['author_key'] == ['OL1A', 'OL2A']
        assert d['author_facet'] ==  ['OL1A Author One', 'OL2A Author Two']
        assert d['author_alternative_name'] == ["Author 1"]

