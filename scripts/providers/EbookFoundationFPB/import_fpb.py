import requests
import time

from openlibrary.config import load_config
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

# GitHub raw content URL for the JSON file on EbookFoundation
FPB_URL = "https://raw.githubusercontent.com/EbookFoundation/free-programming-books-search/main/fpb.json"  

def fetch_data_from_ebookfoundation(max_retries=10, delay=5):
    attempt = 0
    
    while True:
        try:
            response = requests.get(FPB_URL, timeout=10)
            response.raise_for_status()  # Raise an error if request fails
            return response.json()  # Successfully fetched JSON
        except requests.exceptions.RequestException as e:
            attempt += 1
            print(f"Attempt {attempt}: Failed to fetch JSON ({e}). Retrying in {delay} seconds...")
            time.sleep(delay)  # Wait before retrying
            
            if attempt >= max_retries:
                print("Max retries reached. Exiting...")
                return None  # Return None if max retries are exceeded


def main(ol_config: str):
    """
    :param str ol_config: Path to openlibrary.yml file
    """
    load_config(ol_config)


if __name__ == "__main__":
    FnToCLI(main).run()
