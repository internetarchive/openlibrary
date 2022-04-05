import json

from openlibrary.data.dump import print_dump,pgdecode


class TestPrintDump:
    def test_fixes_prefixes(self, capsys):
        records = [
            {
                "key": "/b/OL1M",
                "type": {"key": "/type/edition"},
                "revision": 1,
                "last_modified": {"value": "2019-01-01T00:00:00.000"},
            },
        ]

        print_dump(map(json.dumps, records))
        assert capsys.readouterr().out.strip() == "\t".join([
            "/type/edition",
            "/books/OL1M",
            "1",
            "2019-01-01T00:00:00.000",
            json.dumps({
                "key": "/books/OL1M",
                "type": {"key": "/type/edition"},
                "revision": 1,
                "last_modified": {"value": "2019-01-01T00:00:00.000"},
            }),
        ])

    def test_excludes_sensitive_pages(self, capsys):
        records = [
            {"key": "/people/foo"},
            {"key": "/user/foo"},
            {"key": "/admin/foo"},
        ]
        print_dump(map(json.dumps, records))
        assert capsys.readouterr().out == ""

    def test_excludes_obsolete_pages(self, capsys):
        records = [
            {"key": "/scan_record/foo"},
            {"key": "/old/what"},
        ]

        print_dump(map(json.dumps, records))
        assert capsys.readouterr().out == ""

class TestPgDecode:
    def test_pgdecode_substitute(self):
        assert pgdecode(r"\n\r\t\\") == "\n\r\t\\"

    def test_pgdecode_ascii_printable(self):
        import string

        assert pgdecode(string.printable) == string.printable
