import re
import time

import requests
from bs4 import BeautifulSoup

from openlibrary.config import load_config
from openlibrary.plugins.upstream.utils import get_marc21_language
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


def detect_inaccessible_books(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
    }

    try:
        response_head = requests.head(url, allow_redirects=True, timeout=10)
        response_code = response_head.status_code

        if response_code == 200:
            return True, f"Page accessible code {response_code}"
        
        response = requests.get(url, allow_redirects=True, timeout=10)
        response_text = response.text
        
        if (not response_text):
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            response_text = response.text
        
        # Check content
        soup = BeautifulSoup(response_text, 'html.parser')
        title_text = soup.title.string if soup.title else "No title found"
        title = title_text.lower().strip()
        
        # Check if title indicates page not found
        if "not found" in title or "404" in title or "error" in title:
            return False, f"Page might be available but contains error content. Title: {title}"
            
        # You could also check for specific error text in the body
        body_text = soup.get_text().lower().strip()[:1000]
        error_phrases = ["page not found", "does not exist", "could not be found"]
        
        for phrase in error_phrases:
            if phrase in body_text:
                return False, f"Page content contains error phrase: '{phrase}'"
        
        return True, f"Page accessible code {response_code}"
        
    except Exception as e:
        return False, f"Error accessing page: {e}"


def scrape_metadata(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
    }

    try:
        # Send HTTP request to fetch the webpage content
        response = requests.get(url, allow_redirects=True, timeout=10)
        response_text = response.text
        
        if (not response_text):
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            response_text = response.text

        # Parse HTML content using BeautifulSoup
        soup = BeautifulSoup(response_text, 'html.parser')

        # Extract Open Graph metadata
        title = soup.find("meta", property="og:title") or soup.find("meta", property="twitter:title") or soup.find("meta", attrs={"name": "title"})
        author = soup.find_all("meta", attrs={"name": "author"})
        publisher = soup.find_all("meta", attrs={"name": "publisher"})
        publish_date = soup.find("meta", attrs={"name": "publisher_date"})
        description = soup.find("meta", property="og:description") or soup.find("meta", property="twitter:description") or soup.find("meta", attrs={"name": "description"})
        cover_image = soup.find("meta", property="og:image") or soup.find("meta", property="twitter:image")

        authors, publishers = [], []
        for a in author:
            if "content" in a and a["content"]:
                authors.append({"name": a["content"].strip()})

        for p in publisher:
            if "content" in p and p["content"]:
                publishers.append(p["content"].strip())

        # Get the content attributes
        metadata = {
            "title": title.get("content", "").strip() if (title) else "",
            "authors": authors,
            "publishers": publishers,
            "publish_date": publish_date.get("content", "").strip() if (publish_date) else "",
            "description": description.get("content", "").strip() if (description) else "",
            "cover": cover_image.get("content", "") if (cover_image) else ""
        }

        return metadata
    except Exception as e:
        return {
            "title": "",
            "authors": [],
            "publishers": [],
            "publish_date": "",
            "description": "",
            "cover": ""
        }


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
                raw_authors = book["author"].split(",") if ("author" in book) else []

                for author in raw_authors:
                    if not author:
                        continue

                    authors.append({"name": fix_text_format(author.strip())})

                notes = "".join(book.get("notes", []))
                format = ""

                if "pdf" in notes.lower():
                    format = "pdf"
                elif "epub" in notes.lower():
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
