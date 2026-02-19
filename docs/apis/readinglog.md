# Reading Log API

The Reading Log API allows developers to programmatically access and manage a user's reading log shelves. Users can add/remove books, check reading progress, and search their reading log.

## Shelves

The reading log has three preset shelves:

| Shelf Name        | URL Key             | ID  | Description                         |
| ----------------- | ------------------- | --- | ----------------------------------- |
| Want to Read      | `want-to-read`      | 1   | Books the user wants to read        |
| Currently Reading | `currently-reading` | 2   | Books the user is currently reading |
| Already Read      | `already-read`      | 3   | Books the user has finished reading |

## Endpoints

### Get Bookshelf Counts

Returns the number of users who have placed a work on each shelf.

```
GET /works/OL{work_id}W/bookshelves.json
```

**Example Request:**

```bash
curl https://openlibrary.org/works/OL1W/bookshelves.json
```

**Example Response:**

```json
{
  "counts": {
    "want_to_read": 1234,
    "currently_reading": 56,
    "already_read": 789
  }
}
```

---

### Add or Remove Book from Shelf

Add or remove a work from a user's reading log shelf.

```
POST /works/OL{work_id}W/bookshelves.json
```

**Query Parameters:**

| Parameter      | Type   | Required | Description                                                                          |
| -------------- | ------ | -------- | ------------------------------------------------------------------------------------ |
| `bookshelf_id` | int    | Yes      | Shelf ID: 1 (Want to Read), 2 (Currently Reading), 3 (Already Read), or -1 to remove |
| `action`       | string | No       | Action type: "add" (default) or "remove"                                             |
| `edition_id`   | string | No       | Specific edition key (e.g., `/books/OL123M`)                                         |
| `dont_remove`  | bool   | No       | If true, don't try to remove existing entry when adding                              |
| `redir`        | bool   | No       | If true and patron not logged in, redirect to login then back to work                |

**Example - Add to Want to Read:**

```bash
curl -X POST "https://openlibrary.org/works/OL123W/bookshelves.json?bookshelf_id=1"
```

**Example - Remove from Shelf:**

```bash
curl -X POST "https://openlibrary.org/works/OL123W/bookshelves.json?bookshelf_id=-1"
```

**Example Response (Success):**

```json
{
  "bookshelves_affected": [1]
}
```

**Authentication Required:** Yes. Requires a logged-in user session (cookies).

---

### Get Public Reading Log

Retrieve a user's public reading log for a specific shelf. This endpoint supports searching.

```
GET /people/{username}/books/{shelf}.json
```

**Parameters:**

| Parameter  | Type  | Description                                                                        |
| ---------- | ----- | ---------------------------------------------------------------------------------- |
| `username` | path  | The Open Library username                                                          |
| `shelf`    | path  | Shelf key: `want-to-read`, `currently-reading`, or `already-read`                  |
| `page`     | query | Page number (default: 1)                                                           |
| `limit`    | query | Results per page (default: 100, max: 100)                                          |
| `q`        | query | Search query (minimum 3 characters). Searches title, author, and other work fields |

**Example Request:**

```bash
curl "https://openlibrary.org/users/jk Rowling/books/want-to-read.json?limit=10"
```

**Example Response:**

```json
{
  "page": 1,
  "numFound": 42,
  "reading_log_entries": [
    {
      "work": {
        "title": "The Catcher in the Rye",
        "key": "/works/OL123W",
        "author_keys": ["/authors/OL456A"],
        "author_names": ["J.D. Salinger"],
        "first_publish_year": 1951,
        "cover_id": 8231856,
        "cover_edition_key": "OL12345678M"
      },
      "logged_edition": "/books/OL789M",
      "logged_date": "2024/01/15, 10:30:00"
    }
  ]
}
```

**Note:** Only returns data if the user has made their reading log public in their account settings.

---

### Create/Update Check-in Event

Record reading progress (start reading, update progress, or finish reading).

```
POST /works/OL{work_id}W/check-ins
```

**Request Body (JSON):**

| Field         | Type   | Required | Description                                                 |
| ------------- | ------ | -------- | ----------------------------------------------------------- |
| `event_type`  | int    | Yes      | 1 = Started, 2 = Updated, 3 = Finished                      |
| `year`        | int    | Yes      | Year of the event                                           |
| `month`       | int    | No       | Month of the event                                          |
| `day`         | int    | No       | Day of the event                                            |
| `edition_key` | string | No       | Specific edition key (e.g., `/books/OL123M`)                |
| `event_id`    | int    | No       | If provided, updates existing event instead of creating new |

**Example - Start Reading:**

```bash
curl -X POST "https://openlibrary.org/works/OL123W/check-ins" \
  -H "Content-Type: application/json" \
  -d '{"event_type": 1, "year": 2024, "month": 6, "day": 15}'
```

**Example Response:**

```json
{
  "status": "ok",
  "id": 42
}
```

**Authentication Required:** Yes.

---

### Delete Check-in Event

Remove a check-in event.

```
DELETE /works/OL{work_id}W/check-ins?event_id={event_id}
```

**Example:**

```bash
curl -X DELETE "https://openlibrary.org/works/OL123W/check-ins?event_id=42"
```

**Authentication Required:** Yes.

---

## JavaScript Example (Browser)

Below is an example of how to interact with the Reading Log API from a browser as a logged-in patron:

```javascript
const BASE_URL = "https://openlibrary.org";

const READING_LOG_IDS = {
  want_to_read: 1,
  currently_reading: 2,
  already_read: 3,
};

async function addToShelf(workId, shelfId) {
  const response = await fetch(
    `${BASE_URL}/works/${workId}/bookshelves.json?bookshelf_id=${shelfId}`,
    { method: "POST", credentials: "include" },
  );
  return response.json();
}

async function removeFromShelf(workId) {
  const response = await fetch(
    `${BASE_URL}/works/${workId}/bookshelves.json?bookshelf_id=-1`,
    { method: "POST", credentials: "include" },
  );
  return response.json();
}

async function getBookshelfCounts(workId) {
  const response = await fetch(`${BASE_URL}/works/${workId}/bookshelves.json`);
  return response.json();
}

async function getPublicReadingLog(
  username,
  shelf,
  page = 1,
  limit = 100,
  query = "",
) {
  const params = new URLSearchParams({ page, limit });
  if (query.length >= 3) params.append("q", query);

  const response = await fetch(
    `${BASE_URL}/people/${username}/books/${shelf}.json?${params}`,
  );
  return response.json();
}

async function createCheckIn(
  workId,
  eventType,
  year,
  month = null,
  day = null,
) {
  const response = await fetch(`${BASE_URL}/works/${workId}/check-ins`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      event_type: eventType,
      year,
      month,
      day,
    }),
  });
  return response.json();
}

async function deleteCheckIn(workId, eventId) {
  const response = await fetch(
    `${BASE_URL}/works/${workId}/check-ins?event_id=${eventId}`,
    { method: "DELETE", credentials: "include" },
  );
  return response.json();
}

// Usage examples:
// Add a book to "Want to Read"
// await addToShelf('OL123W', READING_LOG_IDS.want_to_read);

// Get counts for a work
// const counts = await getBookshelfCounts('OL123W');
// console.log(counts);
// { counts: { want_to_read: 42, currently_reading: 5, already_read: 10 } }

// Get someone's public reading log (searching for "harry potter")
// const log = await getPublicReadingLog('jk Rowling', 'want-to-read', 1, 50, 'harry potter');

// Record that you started reading a book
// await createCheckIn('OL123W', 1, 2024, 6, 15);
```

---

## Important Notes

1. **Authentication**: Endpoints that modify data (`POST`, `DELETE` for bookshelves and check-ins) require a logged-in user session. The browser example uses `credentials: 'include'` to send cookies.

2. **Public vs Private**: The public reading log endpoint only returns data if the user has enabled "Public reading log" in their account preferences.

3. **Search**: The search query (`q` parameter) requires a minimum of 3 characters and searches across titles, authors, and other work fields via Solr.

4. **Rate Limiting**: Please be respectful and avoid bulk downloads. See the [Developer Terms](https://openlibrary.org/developers/api) for usage guidelines.

5. **Edition vs Work**: Some endpoints accept an `edition_id` parameter to track which specific edition of a work the user has on their shelf.

## Related Resources

- [My Books Help](https://openlibrary.org/help/faq/using-library#readinglog)
- [Open Library Developer APIs](https://openlibrary.org/developers/api)
- [Swagger Documentation](/swagger/docs)
