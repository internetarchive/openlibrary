import time
import re
import requests

from openlibrary.plugins.upstream.utils import get_marc21_language
from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

# GitHub raw content URL for the JSON file on EbookFoundation
FPB_URL = "https://raw.githubusercontent.com/EbookFoundation/free-programming-books-search/main/fpb.json"


def fix_text_format(text):
    try:
        text = text.encode('latin1').decode('utf-8', errors='ignore')
    except:
        pass

    text = text.replace("\r\n", "\n")
    text = re.sub(r'\n+', '\n', text)
    return text

def fetch_data_from_ebookfoundation(max_retries=10, delay=5):
    attempt = 0

    while True:
        try:
            response = requests.get(FPB_URL, timeout=10)
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
            new_topics = topics + [fix_text_format(section["section"])]

            # Process entries at the current section level
            for book in section.get("entries", []):
                if "url" not in book:
                    continue

                authors = []
                raw_authors = (
                    book["author"].split(",") if ("author" in book) else []
                )

                for author in raw_authors:
                    if not author:
                        continue

                    authors.append({"name": fix_text_format(author.strip())})
                
                notes = "".join(book.get("notes", []))
                format = ""

                if ("pdf" in notes.lower()):
                    format = "pdf"
                elif ("epub" in notes.lower()):
                    format = "epub"
                else:
                    format = "web" 

                entry = {
                    "title": fix_text_format(book.get("title", "????")),
                    "authors": authors,
                    "source_records": ["EbookFoundation"],
                    "publishers": ["????"],
                    "publish_date": "????",
                    "subjects": new_topics,
                    "providers": [
                        {
                            "url": book["url"],
                            "access": "read",
                            "format": format,
                            "provider_name": "EbookFoundation",
                        }
                    ],
                }

                if language_code and language_code != "????":
                    entry["languages"] = [language_code]

                flat_list.append(entry)

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
                
                language_name = (
                    language_section["language"].get("code", "????")
                    if ("language" in language_section)
                    else "????"
                )

                language_code = get_marc21_language(language_name)

                traverse(language_section["sections"], [], language_code)

    return flat_list

def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)


if __name__ == "__main__":
    FnToCLI(main).run()
