import csv
import json

# File paths
IDS_CSV = "ids_next_to_each_other.csv"  # This has the input file with the two columsna nd uathor apirs
AUTHORS_FILE = (
    "ol_dump_authors.txt"  # OpenLibrary authors data dump (now .txt) (0.5GB usualy)
)
OUTPUT_CSV = "authors_with_works.csv"  # this is the fileit outputs


def load_author_pairs(file_path):
    """reads the input CSV and returns a set of author IDs to like avoid dupliaates and such."""

    author_pairs = []
    author_ids = set()

    with open(file_path, encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader)  # skips the top, with no values

        for row in reader:
            if len(row) < 2:
                continue  # skips rows that aren't filled correctly if any
            id1, id2 = row[0].strip(), row[1].strip()
            author_pairs.append((id1, id2))
            author_ids.update([id1, id2])

    return author_pairs, author_ids


def fetch_author_works(file_path, author_ids):
    """uses the open library dump to get works for all the authors."""
    author_data = {
        author_id: {"num_works": 0, "work_title": None} for author_id in author_ids
    }

    with open(file_path, encoding="utf-8") as file:
        for line in file:
            fields = line.strip().split("\t")
            if len(fields) < 2:
                continue

            author_id = fields[0]
            if author_id not in author_ids:
                continue  # Skip if not in our target list

            try:
                data = json.loads(fields[1])  # Parse JSON
                works = data.get("works", [])

                author_data[author_id]["num_works"] = len(works)
                if len(works) == 1:
                    author_data[author_id]["work_title"] = (
                        works[0].get("title", "").strip().lower()
                    )

            except json.JSONDecodeError:
                continue  # Skip invalid JSON entries

    return author_data


def write_output(file_path, author_pairs, author_data):
    """Writes the output CSV with author details and work information."""
    """ this outputs the author pairs with works and titles"""
    with open(file_path, mode="w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "author_id_1",
                "author_id_2",
                "num_works_1",
                "work_title_1",
                "num_works_2",
                "work_title_2",
            ]
        )

        for id1, id2 in author_pairs:
            data1 = author_data.get(id1, {"num_works": 0, "work_title": None})
            data2 = author_data.get(id2, {"num_works": 0, "work_title": None})

            writer.writerow(
                [
                    id1,
                    id2,
                    data1["num_works"],
                    data1["work_title"] or "",
                    data2["num_works"],
                    data2["work_title"] or "",
                ]
            )


def main():
    print("Loading author pairs from CSV...")
    author_pairs, author_ids = load_author_pairs(IDS_CSV)

    print("Fetching author work details from data dump...")
    author_data = fetch_author_works(AUTHORS_FILE, author_ids)

    print(f"Writing results to {OUTPUT_CSV}...")
    write_output(OUTPUT_CSV, author_pairs, author_data)

    print("Done!")


if __name__ == "__main__":
    main()
