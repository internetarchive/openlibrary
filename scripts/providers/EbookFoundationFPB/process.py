import requests
import time

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
            print(f"Attempt {attempt}: Failed to fetch JSON ({e}). Retrying in {delay} seconds...")
            time.sleep(delay)  # Wait before retrying
            
            if attempt >= max_retries:
                print("Max retries reached. Exiting...")
                return None  # Return None if max retries are exceeded


if __name__ == "__main__":
    # GitHub raw content URL for the JSON file on EbookFoundation
    url = "https://raw.githubusercontent.com/EbookFoundation/free-programming-books-search/main/fpb.json"  
    raw_data = fetch_data_from_ebookfoundation(url)
     