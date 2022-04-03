import json

from openlibrary.data.dump import print_dump


class SpyPrint:
    def __init__(self):
        self.output = []

    def __call__(self, msg: str):
        self.output.append(msg)


class TestPrintDump:
    def test_fixes_prefixes(self):
        records = [
            {
                "key": "/b/OL1M",
                "type": {"key": "/type/edition"},
                "revision": 1,
                "last_modified": {"value": "2019-01-01T00:00:00.000"},
            },
        ]
        spy_print = SpyPrint()

        print_dump(map(json.dumps, records), print=spy_print)
        assert spy_print.output == [
            "\t".join([
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
            ]),
        ]

    def test_excludes_sensitive_pages(self):
        records = [
            {"key": "/people/foo"},
            {"key": "/user/foo"},
            {"key": "/admin/foo"},
        ]
        spy_print = SpyPrint()

        print_dump(map(json.dumps, records), print=spy_print)
        assert spy_print.output == []

    def test_excludes_obsolete_pages(self):
        records = [
            {"key": "/scan_record/foo"},
            {"key": "/old/what"},
        ]
        spy_print = SpyPrint()

        print_dump(map(json.dumps, records), print=spy_print)
        assert spy_print.output == []