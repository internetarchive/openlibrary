import time

import requests

from openlibrary.plugins.upstream.utils import get_marc21_language


def fetch_data_from_ebookfoundation(url, max_retries=10, delay=5):
    """Fetch JSON from a URL, retrying until a successful response is received."""
    attempt = 0

    while True:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()  # Raise an error if request fails
            return response.json()  # Successfully fetched JSON

        except requests.exceptions.RequestException as e:
            attempt += 1
            print(
                f"Attempt {attempt}: Failed to fetch JSON ({e}). Retrying in {delay} seconds..."
            )
            time.sleep(delay)  # Wait before retrying

            if attempt >= max_retries:
                print("Max retries reached. Exiting...")
                return None  # Return None if max retries are exceeded


def flatten_books(data):
    flat_list = []

    def traverse(sections, topics, language_code):
        for section in sections:
            new_topics = topics + [section["section"]]

            # Process entries at the current section level
            for book in section.get("entries", []):
                if "url" not in book:
                    continue

                authors = []
                raw_authors = (
                    book["author"].split(",") if ("author" in book) else ["????"]
                )

                for author in raw_authors:
                    if not author:
                        continue

                    authors.append({"name": author.strip()})

                notes = "".join(book.get("notes", []))
                format = ""

                if "pdf" in notes.lower():
                    format = "pdf"
                elif "epub" in notes.lower():
                    format = "epub"
                else:
                    format = "web"

                flat_list.append(
                    {
                        "title": book.get("title", "????"),
                        "authors": authors,
                        "source_records": ["????"],
                        "publishers": ["????"],
                        "publish_date": "????",
                        "languages": [language_code],
                        "subjects": new_topics,
                        "providers": [
                            {
                                "url": book["url"],
                                "access": "read",
                                "format": format,  # need to work on this
                                "provider_name": "EbookFoundation",
                            }
                        ],
                    }
                )

            if "subsections" not in section or not section["subsections"]:
                continue

            # Process subsections recursively
            traverse(section["subsections"], new_topics, language_code)

    # Start traversing from the root
    for child in data.get("children", []):
        if child["type"] == "books":
            for language_section in child.get("children", []):
                if "sections" not in language_section:
                    continue

                language = (
                    language_section["language"].get("name", "????")
                    if "language" in language_section
                    else "????"
                ).lower()

                if language != "????":
                    language_code = get_marc21_language(language)
                else:
                    language_code = "????"

                traverse(language_section["sections"], [], language_code)

    return flat_list


if __name__ == "__main__":
    # GitHub raw content URL for the JSON file on EbookFoundation
    url = "https://raw.githubusercontent.com/EbookFoundation/free-programming-books-search/main/fpb.json"
    raw_data = fetch_data_from_ebookfoundation(url)
    flat_list = flatten_books(raw_data)
