# Books API

> The Books API provides access to detailed information about books/works in Open Library.

## Endpoints

Open Library provides two related endpoints for book data:

### Works Endpoint (Recommended)

```
GET https://openlibrary.org/works/{id}.json
```

### Books/Edition Endpoint

```
GET https://openlibrary.org/books/{id}.json
```

> **Note:** The `/works/` endpoint returns information about a work (the abstract creative work), while `/books/` returns information about a specific edition. For most use cases, the works endpoint is preferred.

## Path Parameters

| Parameter | Type   | Required | Description                                                                                                                                                                                    |
| --------- | ------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`      | string | Yes      | Work or edition identifier. Can be: <br>• OLID (e.g., `OL27448W`)<br>• ISBN with prefix (e.g., `ISBN:0451526934`)<br>• LCCN (e.g., `LCCN:2001012345`)<br>• OCLC number (e.g., `OCLC:12345678`) |

## Works Response Schema

```json
{
  "key": <string>,
  "title": <string>,
  "description": <object|string>,
  "covers": <integer[]>,
  "subjects": <string[]>,
  "subject_places": <string[]>,
  "subject_people": <string[]>,
  "subject_times": <string[]>,
  "authors": <object[]>,
  "first_publish_date": <string>,
  "links": <object[]>,
  "excerpts": <object[]>,
  "type": <object>
}
```

### Response Fields

| Field                | Type              | Nullable | Description                                             |
| -------------------- | ----------------- | -------- | ------------------------------------------------------- |
| `key`                | string            | No       | Unique Open Library key (e.g., `/works/OL27448W`)       |
| `title`              | string            | No       | Book title                                              |
| `description`        | object or string  | Yes      | Work description. Object has `type` and `value` fields. |
| `covers`             | array of integers | Yes      | Array of cover image IDs                                |
| `subjects`           | array of strings  | Yes      | Subject headings                                        |
| `subject_places`     | array of strings  | Yes      | Geographic locations in the work                        |
| `subject_people`     | array of strings  | Yes      | Characters/people in the work                           |
| `subject_times`      | array of strings  | Yes      | Time periods in the work                                |
| `authors`            | array of objects  | Yes      | Author references with roles                            |
| `first_publish_date` | string            | Yes      | First publication date                                  |
| `links`              | array of objects  | Yes      | Related URLs (Wikipedia, official sites, etc.)          |
| `excerpts`           | array of objects  | Yes      | Notable quotes/excerpts                                 |
| `type`               | object            | No       | Open Library type                                       |

### Nested Fields

**Author object:**

```json
{
  "author": { "key": "/authors/OL26320A" },
  "type": { "key": "/type/author_role" }
}
```

**Description object:**

```json
{
  "type": "/type/text",
  "value": "Book description text..."
}
```

**Link object:**

```json
{
  "title": "Wikipedia",
  "url": "https://en.wikipedia.org/wiki/...",
  "type": { "key": "/type/link" }
}
```

## Example Request

```bash
curl -H "User-Agent: MyApp/1.0 (https://myapp.com; contact@myapp.com)" \
  "https://openlibrary.org/works/OL27448W.json"
```

## Example Response

```json
{
  "description": {
    "type": "/type/text",
    "value": "Originally published from 1954 through 1956, J.R.R. Tolkien's richly complex series..."
  },
  "links": [
    {
      "title": "Wikipedia",
      "url": "https://en.wikipedia.org/wiki/The_Lord_of_the_Rings",
      "type": { "key": "/type/link" }
    },
    {
      "title": "Official Site",
      "url": "http://www.tolkienestate.com/...",
      "type": { "key": "/type/link" }
    }
  ],
  "title": "The Lord of the Rings",
  "covers": [14625765, 11658206, 13120659],
  "subject_places": ["Mordor", "Middle Earth", "Hornburg"],
  "first_publish_date": "September 3, 2001",
  "key": "/works/OL27448W",
  "authors": [
    {
      "author": { "key": "/authors/OL26320A" },
      "type": { "key": "/type/author_role" }
    }
  ],
  "excerpts": [
    {
      "pages": "494",
      "excerpt": "'Battle and war!' said Gandalf. 'Ride on!'"
    }
  ],
  "subjects": [
    "The Lord of the Rings",
    "Fiction",
    "Fantasy fiction",
    "Middle Earth (Imaginary place)"
  ],
  "type": { "key": "/type/work" },
  "subject_times": ["The end of the third age"],
  "cover_edition": { "key": "/books/OL3404981M" },
  "latest_revision": 127,
  "revision": 127,
  "created": {
    "type": "/type/datetime",
    "value": "2009-10-13T02:46:28.838662"
  },
  "last_modified": {
    "type": "/type/datetime",
    "value": "2025-12-17T02:00:18.503660"
  }
}
```

## Using Different ID Types

### By OLID (Work)

```
/works/OL27448W.json
```

### By OLID (Edition)

```
/books/OL3404981M.json
```

### By ISBN

```
/books/ISBN:0451526934.json
/works/ISBN:0451526934.json
```

### By LCCN

```
/books/LCCN:2001012345.json
```

### By OCLC Number

```
/books/OCLC:12345678.json
```

## Related Data

### Get Author Details

Use the author key from the `authors` array:

```bash
curl -H "User-Agent: MyApp/1.0" \
  "https://openlibrary.org/authors/OL26320A.json"
```

### Get Cover Image

Use the cover ID from `covers` array with the [Covers API](./covers.md):

```
https://covers.openlibrary.org/b/id/14625765-M.jpg
```

## Usage Notes

- Works represent the abstract creative work; editions represent specific publications
- The `authors` array contains references, not full author data - use the [Authors API](./authors.md) to get author details
- `subjects`, `subject_places`, `subject_people`, and `subject_times` provide rich metadata for categorization
- Links often include Wikipedia pages, official author sites, and related resources

## Rate Limiting

See the [Authentication Guide](./authentication.md) for information about rate limiting and the required User-Agent header.

## Related Endpoints

- [Search API](./search.md) - Search for books
- [Authors API](./authors.md) - Get author details
- [Subjects API](./subjects.md) - Browse by subject
- [Covers API](./covers.md) - Get cover images
