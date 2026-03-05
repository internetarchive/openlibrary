# Getting Started with the Open Library API

Welcome to the Open Library API! This guide will help you make your first API call in just a few minutes.

## What is the Open Library API?

The Open Library API provides programmatic access to Open Library's vast collection of book data. You can:

- **Search** for books by title, author, subject, or ISBN
- **Retrieve** detailed information about books, authors, and subjects
- **Access** cover images and metadata
- **Explore** subjects and their related works

## Base URL

All API requests start with:

```
https://openlibrary.org
```

This is the base URL for all Open Library API endpoints.

## API Structure

The Open Library API follows REST conventions. Here are the main endpoints:

| Endpoint           | Description             | Example                           |
| ------------------ | ----------------------- | --------------------------------- |
| `/search.json`     | Search for books        | `GET /search.json?q=harry+potter` |
| `/books/{id}`      | Get book details        | `GET /books/OL27448W.json`        |
| `/authors/{id}`    | Get author details      | `GET /authors/OL23919A.json`      |
| `/subjects/{name}` | Get subject information | `GET /subjects/love.json`         |
| `/covers/{id}`     | Get cover images        | `/covers/id/14625765-M.jpg`       |

## Your First API Call

Let's make your first search for books!

API call to### Step 1: Choose Your Tool

You can use any HTTP client. Here are examples:

#### Using curl

```bash
curl "https://openlibrary.org/search.json?q=the+lord+of+the+rings&limit=1"
```

#### Using JavaScript (fetch)

```javascript
const response = await fetch(
  "https://openlibrary.org/search.json?q=the+lord+of+the+rings&limit=1",
  {
    headers: {
      "User-Agent": "MyApp/1.0 (https://myapp.com; contact@myapp.com)",
    },
  },
);
const data = await response.json();
console.log(data);
```

#### Using Python (requests)

```python
import requests

response = requests.get(
    'https://openlibrary.org/search.json',
    params={'q': 'the lord of the rings', 'limit': 1},
    headers={'User-Agent': 'MyApp/1.0'}
)
data = response.json()
print(data)
```

> **Note:** The `User-Agent` header is required. See the [Authentication Guide](./authentication.md) for details.

### Step 2: Understand the Response

A successful response returns a JSON object like this:

```json
{
  "numFound": 899,
  "start": 0,
  "docs": [
    {
      "key": "/works/OL27448W",
      "title": "The Lord of the Rings",
      "author_name": ["J.R.R. Tolkien"],
      "first_publish_year": 1954,
      "cover_i": 14625765,
      "edition_count": 251,
      "language": ["eng", "ger", "fre", "spa", ...]
    }
  ]
}
```

### Step 3: Explore the Response Fields

The search response includes these useful fields:

| Field                | Description                                       |
| -------------------- | ------------------------------------------------- |
| `numFound`           | Total number of results found                     |
| `docs`               | Array of book results                             |
| `key`                | Unique Open Library key (e.g., `/works/OL27448W`) |
| `title`              | Book title                                        |
| `author_name`        | Array of author names                             |
| `first_publish_year` | Year the book was first published                 |
| `cover_i`            | Cover image ID                                    |
| `edition_count`      | Number of editions available                      |

## No API Key Required

The Open Library API is free and open — **no API key is required**. However, you must include a `User-Agent` header that identifies your application.

This helps Open Library:

- Track usage patterns
- Contact you if your application causes issues
- Apply fair rate limits across all users

## Next Steps

Now that you've made your first call:

1. **Read the [Authentication Guide](./authentication.md)** — Learn why User-Agent is required and best practices
2. **Handle Errors & Rate Limits** — Review the [Error Handling Guide](./errors.md) to build robust applications
3. **Explore the Search API** — Try different query parameters like `author`, `subject`, `isbn`, or `title`
4. **Get Book Details** — Use the `key` from search results to fetch full book information
5. **Browse Authors** — Use author keys to get author biographies and their works

## Quick Reference

```
Base URL:     https://openlibrary.org
Search:       https://openlibrary.org/search.json
Book:         https://openlibrary.org/books/{id}
Author:       https://openlibrary.org/authors/{id}
Subject:      https://openlibrary.org/subjects/{name}
Covers:       https://covers.openlibrary.org/b/id/{id}-M.jpg
```

Happy exploring!
