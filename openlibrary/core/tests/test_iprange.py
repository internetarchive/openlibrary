from .. import iprange

def test_parse_ip_ranges():
    def f(text):
        return list(iprange.parse_ip_ranges(text))
    assert f("1.2.3.4") == ["1.2.3.4"]
    assert f("1.2.3 - 4.*") == [("1.2.3.0", "1.2.4.255")]
    assert f("1.2.3.4-10") == [("1.2.3.4", "1.2.3.10")]
    assert f("1.2.3.4 - 2.3.4.40") == [("1.2.3.4", "2.3.4.40")]
    assert f("1.2.*.* ") == ["1.2.0.0/16"]
    assert f("1.2.3.* ") == ["1.2.3.0/24"]

class TestIPDict:
    def test_simple(self):
        d = iprange.IPDict()
        d.add_ip_range("1.2.3.0/24", "foo")
        
        assert d.get("1.2.3.4") == "foo"
        assert d.get("1.2.3.44") == "foo"
        assert d.get("1.2.4.5") == None
        assert d.get("100.2.4.5") == None

    def test_add_ip_range_text(self):
        text = (
            "#ip ranges\n" +
            "1.2.3.0/24\n" +
            "9.8.*.*")
        
        d = iprange.IPDict()
        d.add_ip_range_text(text, 'foo')
        
        assert '1.2.3.2' in d
        assert '1.2.4.2' not in d
        assert '9.8.1.2' in d
        assert '9.8.3.2' in d
        assert '9.9.3.2' not in d