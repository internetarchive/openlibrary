# Search API

> The Search API allows you to search for books across Open Library's entire catalog.

## Endpoint

```
GET https://openlibrary.org/search.json
```

## Query Parameters

The Search API supports the following query parameters:

| Parameter | Type    | Required | Description                                                               |
| --------- | ------- | -------- | ------------------------------------------------------------------------- |
| `q`       | string  | Yes\*    | General search query. Searches across title, author, and subject.         |
| `title`   | string  | No\*     | Search specifically in book titles.                                       |
| `author`  | string  | No\*     | Search specifically by author name.                                       |
| `subject` | string  | No\*     | Search specifically by subject.                                           |
| `isbn`    | string  | No\*     | Search by ISBN (10 or 13 digits).                                         |
| `limit`   | integer | No       | Number of results to return (default: 50, max: 1000).                     |
| `offset`  | integer | No       | Number of results to skip (for pagination).                               |
| `fields`  | string  | No       | Comma-separated list of fields to return (e.g., `key,title,author_name`). |
| `page`    | integer | No       | Page number (alternative to offset).                                      |
| `sort`    | string  | No       | Sort order: `relevance`, `oldest`, `newest`.                              |

> - At least one of `q`, `title`, `author`, `subject`, or `isbn` is required.

## Response Schema

The Search API returns a JSON object with the following structure:

```json
{
  "numFound": <integer>,
  "start": <integer>,
  "numFoundExact": <boolean>,
  "docs": [
    {
      "key": <string>,
      "title": <string>,
      "author_name": <string[]|null>,
      "author_key": <string[]|null>,
      "first_publish_year": <integer|null>,
      "cover_i": <integer|null>,
      "edition_count": <integer|null>,
      "isbn": <string[]|null>,
      "language": <string[]|null>,
      "subject": <string[]|null>,
      "publisher": <string[]|null>
    }
  ]
}
```

### Response Fields

| Field           | Type    | Description                                 |
| --------------- | ------- | ------------------------------------------- |
| `numFound`      | integer | Total number of results matching the query  |
| `start`         | integer | Offset of the first result in this response |
| `numFoundExact` | boolean | Whether `numFound` is exact or estimated    |
| `docs`          | array   | Array of book documents matching the query  |

### Document Fields (each item in `docs` array)

| Field                | Type             | Nullable | Description                                       |
| -------------------- | ---------------- | -------- | ------------------------------------------------- |
| `key`                | string           | No       | Unique Open Library key (e.g., `/works/OL27448W`) |
| `title`              | string           | No       | Book title                                        |
| `author_name`        | array of strings | Yes      | Array of author names                             |
| `author_key`         | array of strings | Yes      | Array of author OLIDs                             |
| `first_publish_year` | integer          | Yes      | Year of first publication                         |
| `cover_i`            | integer          | Yes      | Cover image ID (use with Covers API)              |
| `edition_count`      | integer          | Yes      | Number of editions available                      |
| `isbn`               | array of strings | Yes      | ISBNs associated with the work                    |
| `language`           | array of strings | Yes      | Language codes                                    |
| `subject`            | array of strings | Yes      | Subject headings                                  |
| `publisher`          | array of strings | Yes      | Publisher names                                   |

## Example Request

```bash
curl -H "User-Agent: MyApp/1.0 (https://myapp.com; contact@myapp.com)" \
  "https://openlibrary.org/search.json?q=lord+of+the+rings&limit=2&fields=key,title,author_name,first_publish_year,cover_i"
```

## Example Response

```json
{
  "numFound": 929,
  "start": 0,
  "numFoundExact": true,
  "docs": [
    {
      "key": "/works/OL27448W",
      "title": "The Lord of the Rings",
      "author_name": ["J.R.R. Tolkien"],
      "author_key": ["OL26320A"],
      "first_publish_year": 1954,
      "cover_i": 14625765,
      "edition_count": 251
    },
    {
      "key": "/works/OL9886W",
      "title": "The Lord of the Rings",
      "author_name": ["J.R.R. Tolkien"],
      "author_key": ["OL26320A"],
      "first_publish_year": 1995,
      "cover_i": 2920827,
      "edition_count": 32
    }
  ]
}
```

## Code Examples

### JavaScript (fetch)

```javascript
/**
 * Search Open Library for books
 * @param {string} query - General search query
 * @param {number} limit - Number of results to return
 */
async function searchOpenLibrary(query, limit = 2) {
  const url = `https://openlibrary.org/search.json?q=${encodeURIComponent(query)}&limit=${limit}&fields=key,title,author_name,first_publish_year,cover_i`;

  try {
    const response = await fetch(url, {
      headers: {
        // Required: Identify your application
        "User-Agent": "MyApp/1.0 (https://myapp.com; contact@myapp.com)",
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log(`Found ${data.numFound} results:`);

    data.docs.forEach((book) => {
      console.log(
        `- ${book.title} (${book.first_publish_year}) by ${book.author_name?.join(", ") || "Unknown"}`,
      );
    });

    return data;
  } catch (error) {
    console.error("Search failed:", error);
  }
}

// Example usage:
searchOpenLibrary("lord of the rings");
```

### Python (requests)

```python
import requests

def search_open_library(query, limit=2):
    """
    Search Open Library for books using the requests library.
    """
    url = 'https://openlibrary.org/search.json'
    params = {
        'q': query,
        'limit': limit,
        'fields': 'key,title,author_name,first_publish_year,cover_i'
    }
    headers = {
        # Required: Identify your application
        'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()

        data = response.json()
        print(f"Found {data.get('numFound')} results:")

        for book in data.get('docs', []):
            title = book.get('title')
            year = book.get('first_publish_year')
            authors = ", ".join(book.get('author_name', ['Unknown']))
            print(f"- {title} ({year}) by {authors}")

        return data
    except requests.exceptions.RequestException as e:
        print(f"Search failed: {e}")

# Example usage:
if __name__ == "__main__":
    search_open_library('lord of the rings')
```

## Usage Notes

- Use the `fields` parameter to reduce response size and improve performance
- The `cover_i` value can be used with the [Covers API](./covers.md) to retrieve cover images
- The `key` value (e.g., `/works/OL27448W`) can be used with the [Books API](./books.md) to get full work details
- Author keys (e.g., `OL26320A`) can be used with the [Authors API](./authors.md) to get author details

## Rate Limiting

See the [Authentication Guide](./authentication.md) for information about rate limiting and the required User-Agent header.

## Related Endpoints

- [Books API](./books.md) - Get detailed book information
- [Authors API](./authors.md) - Get author details
- [Covers API](./covers.md) - Get cover images
