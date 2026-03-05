# Subjects API

> The Subjects API provides access to information about subjects (topics, themes, genres) and their associated works in Open Library.

## Endpoint

```
GET https://openlibrary.org/subjects/{name}.json
```

## Path Parameters

| Parameter | Type   | Required | Description                                                                              |
| --------- | ------ | -------- | ---------------------------------------------------------------------------------------- |
| `name`    | string | Yes      | Subject name. Spaces should be replaced with underscores. URL-encode special characters. |

## URL Encoding

Subject names must be URL-encoded. Use underscores for spaces:

| Subject                         | URL                                            |
| ------------------------------- | ---------------------------------------------- |
| `love`                          | `/subjects/love.json`                          |
| `science fiction`               | `/subjects/science_fiction.json`               |
| `detective and mystery stories` | `/subjects/detective_and_mystery_stories.json` |

For special characters, use standard URL encoding:

- `%20` for spaces (or use underscores)
- `%27` for apostrophes (e.g., `women%27s_studies`)

## Query Parameters

| Parameter | Type    | Required | Description                                       |
| --------- | ------- | -------- | ------------------------------------------------- |
| `limit`   | integer | No       | Number of works to return (default: 10, max: 100) |
| `offset`  | integer | No       | Number of works to skip (for pagination)          |
| `fields`  | string  | No       | Comma-separated fields to return                  |

## Response Schema

```json
{
  "key": <string>,
  "name": <string>,
  "subject_type": <string>,
  "solr_query": <string>,
  "work_count": <integer>,
  "works": [
    {
      "key": <string>,
      "title": <string>,
      "edition_count": <integer>,
      "cover_id": <integer|null>,
      "cover_edition_key": <string|null>,
      "subject": <string[]>,
      "authors": <object[]>,
      "first_publish_year": <integer|null>,
      "ia": <string[]>,
      "public_scan": <boolean>,
      "has_fulltext": <boolean>,
      "availability": <object>
    }
  ]
}
```

### Response Fields

| Field          | Type             | Nullable | Description                                          |
| -------------- | ---------------- | -------- | ---------------------------------------------------- |
| `key`          | string           | No       | Subject URL path (e.g., `/subjects/love`)            |
| `name`         | string           | No       | Subject display name                                 |
| `subject_type` | string           | No       | Type of subject (e.g., `subject`, `place`, `person`) |
| `solr_query`   | string           | No       | Internal Solr query string                           |
| `work_count`   | integer          | No       | Total number of works with this subject              |
| `works`        | array of objects | No       | Array of works under this subject                    |

### Work Object Fields

| Field                | Type             | Nullable | Description                        |
| -------------------- | ---------------- | -------- | ---------------------------------- |
| `key`                | string           | No       | Work key (e.g., `/works/OL21177W`) |
| `title`              | string           | No       | Book title                         |
| `edition_count`      | integer          | Yes      | Number of editions                 |
| `cover_id`           | integer          | Yes      | Cover image ID                     |
| `cover_edition_key`  | string           | Yes      | Edition key for cover              |
| `subject`            | array of strings | Yes      | Subject headings                   |
| `authors`            | array of objects | Yes      | Author references                  |
| `first_publish_year` | integer          | Yes      | Year first published               |
| `ia`                 | array of strings | Yes      | Internet Archive IDs               |
| `public_scan`        | boolean          | No       | Whether a public scan exists       |
| `has_fulltext`       | boolean          | No       | Whether full text is available     |
| `availability`       | object           | No       | Lending/availability info          |

### Availability Object

```json
{
  "status": "open|borrowable|unavailable",
  "available_to_browse": <boolean>,
  "available_to_borrow": <boolean>,
  "available_to_waitlist": <boolean>,
  "is_printdisabled": <boolean>,
  "is_readable": <boolean>,
  "is_lendable": <boolean>,
  "identifier": <string|null>,
  "openlibrary_work": <string>,
  "openlibrary_edition": <string>
}
```

## Example Request

```bash
curl -H "User-Agent: MyApp/1.0 (https://myapp.com; contact@myapp.com)" \
  "https://openlibrary.org/subjects/love.json?limit=2"
```

## Example Response

```json
{
  "key": "/subjects/love",
  "name": "love",
  "subject_type": "subject",
  "solr_query": "subject_key:\"love\"",
  "work_count": 18585,
  "works": [
    {
      "key": "/works/OL21177W",
      "title": "Wuthering Heights",
      "edition_count": 2886,
      "cover_id": 12818862,
      "cover_edition_key": "OL38586477M",
      "subject": [
        "love",
        "romance",
        "revenge",
        "Fiction",
        "English literature"
      ],
      "authors": [{ "key": "/authors/OL24529A", "name": "Emily Brontë" }],
      "first_publish_year": 1846,
      "ia": ["wutheringheights0000kesh"],
      "public_scan": true,
      "has_fulltext": true,
      "availability": {
        "status": "open",
        "available_to_browse": false,
        "available_to_borrow": false,
        "available_to_waitlist": false,
        "is_printdisabled": false,
        "is_readable": true,
        "is_lendable": false,
        "is_previewable": true,
        "identifier": "wutheringheights0000kesh",
        "openlibrary_work": "OL21177W",
        "openlibrary_edition": "OL57648863M"
      }
    }
  ]
}
```

## Code Examples

### JavaScript (fetch)

```javascript
/**
 * Fetch works by subject
 * @param {string} subject - Subject name (e.g., love, science_fiction)
 * @param {number} limit - Number of works to return
 */
async function fetchSubject(subject, limit = 2) {
  const url = `https://openlibrary.org/subjects/${encodeURIComponent(subject)}.json?limit=${limit}`;

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
    console.log(`Found ${data.work_count} works for subject "${data.name}":`);

    data.works.forEach((work) => {
      const authors = work.authors?.map((a) => a.name).join(", ") || "Unknown";
      console.log(`- ${work.title} by ${authors}`);
    });

    return data;
  } catch (error) {
    console.error("Fetch failed:", error);
  }
}

// Example usage:
fetchSubject("love");
```

### Python (requests)

```python
import requests

def fetch_subject(subject, limit=2):
    """
    Fetch works by subject using the requests library.
    """
    # Replace spaces with underscores
    formatted_subject = subject.replace(' ', '_')
    url = f'https://openlibrary.org/subjects/{formatted_subject}.json'
    params = {'limit': limit}
    headers = {
        # Required: Identify your application
        'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()

        data = response.json()
        print(f"Found {data.get('work_count')} works for subject \"{data.get('name')}\":")

        for work in data.get('works', []):
            title = work.get('title')
            authors = ", ".join([a.get('name') for a in work.get('authors', []) if a.get('name')])
            print(f"- {title} by {authors or 'Unknown'}")

        return data
    except requests.exceptions.RequestException as e:
        print(f"Fetch failed: {e}")

# Example usage:
if __name__ == "__main__":
    fetch_subject('love')
```

## Subject Types

The API supports different subject types:

| Type      | Description           | Example                              |
| --------- | --------------------- | ------------------------------------ |
| `subject` | General topics/themes | `science_fiction`, `love`, `mystery` |
| `place`   | Geographic locations  | `england`, `paris`, `united_states`  |
| `person`  | Named individuals     | `sherlock_holmes`, `napoleon`        |
| `time`    | Historical periods    | `renaissance`, `world_war_ii`        |

## Common Subject Patterns

### Genres

```
/subjects/science_fiction.json
/subjects/fantasy.json
/subjects/mystery_and_detective_stories.json
/subjects/romance_fiction.json
/subjects/horror_tales.json
```

### Places

```
/subjects/england.json
/subjects/united_states.json
/subjects/paris_france.json
/subjects/japan.json
```

### Time Periods

```
/subjects/renaissance.json
/subjects/victorian_era.json
/subjects/world_war_ii.json
/subjects/21st_century.json
```

## Pagination

To paginate through results:

```bash
# First page
curl "https://openlibrary.org/subjects/love.json?limit=10"

# Next page (skip first 10)
curl "https://openlibrary.org/subjects/love.json?limit=10&offset=10"
```

The response includes `work_count` so you know how many total works exist.

## Getting Full Work Details

Use the `key` from works to get full details via the [Books API](./books.md):

```
/works/OL21177W.json
```

## Getting Cover Images

Use `cover_id` with the [Covers API](./covers.md):

```
https://covers.openlibrary.org/b/id/12818862-M.jpg
```

## Usage Notes

- Replace spaces with underscores in subject names
- Subject searches are case-insensitive
- The `work_count` can help determine if a subject has enough results
- Use `public_scan` and `has_fulltext` to filter for works with available text
- The `availability` object indicates lending options for each work

## Rate Limiting

See the [Authentication Guide](./authentication.md) for information about rate limiting and the required User-Agent header.

## Related Endpoints

- [Search API](./search.md) - Search with subject filter
- [Books API](./books.md) - Get full work details
- [Authors API](./authors.md) - Get author details
- [Covers API](./covers.md) - Get cover images
