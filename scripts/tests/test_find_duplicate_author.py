"""Tests for scripts/find_duplicate_author.py"""

__author__ = "Maifee Ul Asad"

import csv
import gzip
import json

from ..find_duplicate_author import (
    extract_id_number,
    find_duplicate_chains,
    get_author_work_info,
    load_author_ids_from_csv,
    load_dump_file,
    write_matches,
)


class TestExtractIdNumber:
    def test_plain_id(self):
        assert extract_id_number("OL7133991A") == 7133991

    def test_with_authors_prefix(self):
        assert extract_id_number("/authors/OL7133991A") == 7133991

    def test_no_match_returns_none(self):
        assert extract_id_number("not-an-id") is None

    def test_zero_id(self):
        assert extract_id_number("OL0A") == 0


class TestFindDuplicateChains:
    def test_consecutive_chain_of_three(self):
        authors_data = [
            ("OL1A", "Jane Doe", 0, ""),
            ("OL2A", "Jane Doe", 0, ""),
            ("OL3A", "Jane Doe", 0, ""),
        ]
        matches = find_duplicate_chains(authors_data, use_title_matching=False)
        assert len(matches) == 1
        name, _title, chain = matches[0]
        assert name == "Jane Doe"
        assert chain == ["OL1A", "OL2A", "OL3A"]

    def test_non_consecutive_ids_not_chained(self):
        authors_data = [
            ("OL1A", "Jane Doe", 0, ""),
            ("OL3A", "Jane Doe", 0, ""),
        ]
        matches = find_duplicate_chains(authors_data, use_title_matching=False)
        assert matches == []

    def test_different_names_not_grouped(self):
        authors_data = [
            ("OL1A", "Jane Doe", 0, ""),
            ("OL2A", "John Smith", 0, ""),
        ]
        matches = find_duplicate_chains(authors_data, use_title_matching=False)
        assert matches == []

    def test_single_author_not_a_duplicate(self):
        authors_data = [("OL1A", "Jane Doe", 0, "")]
        matches = find_duplicate_chains(authors_data, use_title_matching=False)
        assert matches == []

    def test_title_matching_requires_single_matching_work(self):
        authors_data = [
            ("OL1A", "Jane Doe", 1, "My Book"),
            ("OL2A", "Jane Doe", 1, "my book"),
        ]
        matches = find_duplicate_chains(authors_data, use_title_matching=True)
        assert len(matches) == 1
        _name, title, chain = matches[0]
        assert title == "my book"
        assert chain == ["OL1A", "OL2A"]

    def test_title_matching_excludes_multi_work_authors(self):
        authors_data = [
            ("OL1A", "Jane Doe", 2, "My Book"),
            ("OL2A", "Jane Doe", 2, "My Book"),
        ]
        matches = find_duplicate_chains(authors_data, use_title_matching=True)
        assert matches == []


class TestLoadAuthorIdsFromCsv:
    def test_loads_rows(self, tmp_path):
        csv_path = tmp_path / "authors.csv"
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["/authors/OL1A", " Jane Doe "])
            writer.writerow(["/authors/OL2A", "John Smith"])

        authors = load_author_ids_from_csv(csv_path)
        assert authors == [
            ("/authors/OL1A", "Jane Doe"),
            ("/authors/OL2A", "John Smith"),
        ]

    def test_skips_short_rows(self, tmp_path):
        csv_path = tmp_path / "authors.csv"
        with csv_path.open("w", newline="") as f:
            f.write("/authors/OL1A\n")

        assert load_author_ids_from_csv(csv_path) == []


class TestWriteMatches:
    def test_writes_with_titles(self, tmp_path):
        matches_path = tmp_path / "matches.csv"
        write_matches(
            [("Jane Doe", "my book", ["OL1A", "OL2A"])],
            matches_path,
            include_titles=True,
        )

        with matches_path.open() as f:
            rows = list(csv.reader(f))

        assert rows[0] == ["author_name", "work_title", "duplicate_count", "author_ids"]
        assert rows[1] == ["Jane Doe", "my book", "2", "OL1A|OL2A"]

    def test_writes_without_titles(self, tmp_path):
        matches_path = tmp_path / "matches.csv"
        write_matches(
            [("Jane Doe", "", ["OL1A", "OL2A"])],
            matches_path,
            include_titles=False,
        )

        with matches_path.open() as f:
            rows = list(csv.reader(f))

        assert rows[0] == ["author_name", "duplicate_count", "author_ids"]
        assert rows[1] == ["Jane Doe", "2", "OL1A|OL2A"]


class TestLoadDumpFile:
    def test_loads_plain_jsonl(self, tmp_path):
        dump_path = tmp_path / "authors.jsonl"
        with dump_path.open("w") as f:
            f.write(json.dumps({"key": "/authors/OL1A", "works": []}) + "\n")
            f.write("\n")  # blank lines are skipped
            f.write("not json\n")  # invalid lines are skipped

        records = load_dump_file(dump_path, "/authors/")
        assert records == {"OL1A": {"key": "/authors/OL1A", "works": []}}

    def test_loads_gzipped_jsonl(self, tmp_path):
        dump_path = tmp_path / "authors.jsonl.gz"
        with gzip.open(dump_path, "wt") as f:
            f.write(json.dumps({"key": "/authors/OL1A", "works": []}) + "\n")

        records = load_dump_file(dump_path, "/authors/")
        assert records == {"OL1A": {"key": "/authors/OL1A", "works": []}}


class TestGetAuthorWorkInfo:
    def test_no_works(self):
        assert get_author_work_info("OL1A", {"OL1A": {"works": []}}, {}) == (0, "")

    def test_inline_work_title(self):
        authors_db = {"OL1A": {"works": [{"title": "My Book"}]}}
        assert get_author_work_info("OL1A", authors_db, {}) == (1, "My Book")

    def test_work_reference_resolved_from_works_db(self):
        authors_db = {"OL1A": {"works": ["/works/OL10W"]}}
        works_db = {"OL10W": {"title": "My Book"}}
        assert get_author_work_info("OL1A", authors_db, works_db) == (1, "My Book")

    def test_unknown_author(self):
        assert get_author_work_info("OL404A", {}, {}) == (0, "")
