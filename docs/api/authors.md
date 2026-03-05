# Authors API

> The Authors API provides access to detailed information about authors in Open Library.

## Endpoint

```
GET https://openlibrary.org/authors/{id}.json
```

## Path Parameters

| Parameter | Type   | Required | Description                                   |
| --------- | ------ | -------- | --------------------------------------------- |
| `id`      | string | Yes      | Author identifier (OLID). Example: `OL23919A` |

## Response Schema

```json
{
  "key": <string>,
  "name": <string>,
  "personal_name": <string|null>,
  "birth_date": <string|null>,
  "death_date": <string|null>,
  "title": <string|null>,
  "fuller_name": <string|null>,
  "bio": <object|string|null>,
  "photos": <integer[]>,
  "links": <object[]>,
  "alternate_names": <string[]>,
  "remote_ids": <object>,
  "entity_type": <string>,
  "source_records": <string[]>,
  "type": <object>
}
```

### Response Fields

| Field             | Type              | Nullable | Description                                                  |
| ----------------- | ----------------- | -------- | ------------------------------------------------------------ |
| `key`             | string            | No       | Unique Open Library key (e.g., `/authors/OL23919A`)          |
| `name`            | string            | No       | Full name as displayed                                       |
| `personal_name`   | string            | Yes      | Personal/legal name                                          |
| `birth_date`      | string            | Yes      | Birth date (various formats)                                 |
| `death_date`      | string            | Yes      | Death date (various formats)                                 |
| `title`           | string            | Yes      | Title (e.g., "OBE", "Sir")                                   |
| `fuller_name`     | string            | Yes      | Full name with titles                                        |
| `bio`             | object or string  | Yes      | Biography. Object has `type` and `value` fields.             |
| `photos`          | array of integers | Yes      | Photo IDs (positive = user-uploaded, negative = from source) |
| `links`           | array of objects  | Yes      | Related URLs (Wikipedia, official site, etc.)                |
| `alternate_names` | array of strings  | Yes      | Alternative name spellings/pseudonyms                        |
| `remote_ids`      | object            | Yes      | External IDs (Goodreads, Wikidata, etc.)                     |
| `entity_type`     | string            | Yes      | Type of entity (e.g., "person", "org")                       |
| `source_records`  | array of strings  | Yes      | Original data sources                                        |
| `type`            | object            | No       | Open Library type                                            |

### Nested Fields

**Bio object:**

```json
{
  "type": "/type/text",
  "value": "Author biography text..."
}
```

**Link object:**

```json
{
  "title": "Official Site",
  "url": "https://example.com",
  "type": { "key": "/type/link" }
}
```

**remote_ids object:**

```json
{
  "viaf": "116796842",
  "goodreads": "1077326",
  "wikidata": "Q34660",
  "librarything": "rowlingjk",
  "amazon": "B000AP9A6K",
  "imdb": "nm0746830"
}
```

## Example Request

```bash
curl -H "User-Agent: MyApp/1.0 (https://myapp.com; contact@myapp.com)" \
  "https://openlibrary.org/authors/OL23919A.json"
```

## Example Response

```json
{
  "birth_date": "31 July 1965",
  "fuller_name": "Joanne \"Jo\" Rowling",
  "photos": [5543033, -1],
  "links": [
    {
      "title": "Official Site",
      "url": "http://www.jkrowling.com/",
      "type": { "key": "/type/link" }
    }
  ],
  "entity_type": "person",
  "personal_name": "J. K. Rowling",
  "title": "OBE",
  "key": "/authors/OL23919A",
  "bio": {
    "type": "/type/text",
    "value": "Joanne \"Jo\" Murray, OBE (née Rowling), better known under the pen name J. K. Rowling, is a British author best known as the creator of the Harry Potter fantasy series..."
  },
  "alternate_names": [
    "Joanne Rowling",
    "Joanne K. Rowling",
    "JK Rowling",
    "Robert Galbraith",
    "J.K. Rowling"
  ],
  "remote_ids": {
    "viaf": "116796842",
    "goodreads": "1077326",
    "wikidata": "Q34660",
    "librarything": "rowlingjk",
    "amazon": "B000AP9A6K",
    "imdb": "nm0746830",
    "isni": "000000012148628X",
    "lc_naf": "n97108433"
  },
  "type": { "key": "/type/type" },
  "name": "J. K. Rowling",
  "latest_revision": 130,
  "revision": 130,
  "created": {
    "type": "/type/datetime",
    "value": "2008-04-01T03:28:50.625462"
  },
  "last_modified": {
    "type": "/type/datetime",
    "value": "2026-01-12T17:50:44.063267"
  }
}
```

## Code Examples

### JavaScript (fetch)

```javascript
/**
 * Fetch author details by Open Library ID (OLID)
 * @param {string} olid - Author identifier (e.g., OL23919A)
 */
async function fetchAuthor(olid) {
  const url = `https://openlibrary.org/authors/${olid}.json`;

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
    console.log(`Author: ${data.name}`);

    // Handle bio object or string
    const bio = typeof data.bio === "object" ? data.bio.value : data.bio;

    console.log(`Bio: ${bio?.substring(0, 100)}...`);

    return data;
  } catch (error) {
    console.error("Fetch failed:", error);
  }
}

// Example usage:
fetchAuthor("OL23919A");
```

### Python (requests)

```python
import requests

def fetch_author(olid):
    """
    Fetch author details by Open Library ID (OLID) using the requests library.
    """
    url = f'https://openlibrary.org/authors/{olid}.json'
    headers = {
        # Required: Identify your application
        'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        print(f"Author: {data.get('name')}")

        # Handle bio object or string
        bio = data.get('bio', '')
        if isinstance(bio, dict):
            bio = bio.get('value', '')

        print(f"Bio: {bio[:100]}...")

        return data
    except requests.exceptions.RequestException as e:
        print(f"Fetch failed: {e}")

# Example usage:
if __name__ == "__main__":
    fetch_author('OL23919A')
```

## Author Works Endpoint

To get a list of works by an author, use the works endpoint:

```
GET https://openlibrary.org/authors/{id}/works.json
```

### Query Parameters

| Parameter | Type    | Required | Description                                        |
| --------- | ------- | -------- | -------------------------------------------------- |
| `limit`   | integer | No       | Number of works to return (default: 25, max: 1000) |
| `offset`  | integer | No       | Number of works to skip                            |
| `fields`  | string  | No       | Comma-separated fields to return                   |

### Works Response Schema

```json
{
  "size": <integer>,
  "links": {
    "self": <string>,
    "author": <string>,
    "next": <string|null>
  },
  "entries": [
    {
      "key": <string>,
      "title": <string>,
      "type": <object>
    }
  ]
}
```

### Example: Author Works

```bash
curl -H "User-Agent: MyApp/1.0" \
  "https://openlibrary.org/authors/OL23919A/works.json?limit=2"
```

```json
{
  "links": {
    "self": "/authors/OL23919A/works.json?limit=2",
    "author": "/authors/OL23919A",
    "next": "/authors/OL23919A/works.json?limit=2&offset=2"
  },
  "size": 406,
  "entries": [
    {
      "type": { "key": "/type/work" },
      "title": "Harry Potter and the Half-Blood Prince (SparkNotes Literature Guide)",
      "authors": [
        {
          "type": { "key": "/type/author_role" },
          "author": { "key": "/authors/OL2964716A" }
        },
        {
          "type": { "key": "/type/author_role" },
          "author": { "key": "/authors/OL23919A" }
        }
      ],
      "key": "/works/OL29423026W"
    }
  ]
}
```

## Author Photos

To get an author's photo, use the positive photo ID from the `photos` array:

```
https://covers.openlibrary.org/a/olid/OL23919A-L.jpg
```

Available sizes: `S` (small), `M` (medium), `L` (large)

## Finding Author OLIDs

1. Use the [Search API](./search.md) and look for `author_key` in results
2. Use the `remote_ids` to cross-reference with external services (Goodreads, Wikidata, etc.)

## Usage Notes

- The `photos` array may contain positive IDs (user-uploaded) and negative IDs (from external sources)
- `alternate_names` includes pseudonyms (e.g., J.K. Rowling writes as "Robert Galbraith")
- `remote_ids` provides cross-references to other library databases
- The author works endpoint supports pagination via `offset` parameter

## Rate Limiting

See the [Authentication Guide](./authentication.md) for information about rate limiting and the required User-Agent header.

## Related Endpoints

- [Search API](./search.md) - Search for books by author
- [Books API](./books.md) - Get book details
- [Covers API](./covers.md) - Get author photos and book covers
