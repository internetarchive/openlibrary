# Open Library API Documentation

Welcome to the Open Library API documentation. This guide provides practical examples and explanations to help you integrate with the Open Library platform.

## Table of Contents
- [Quick Start](#quick-start)
- [Authentication](#authentication)
- [Books API](#books-api)
- [Authors API](#authors-api)
- [Search API](#search-api)
- [Covers API](#covers-api)
- [Response Formats & Error Handling](#response-formats--error-handling)

---

## Quick Start

The Open Library API is primarily RESTful and returns data in JSON format. Most GET requests do not require authentication.

**Base URL:** `https://openlibrary.org`

### Example: Fetching a book by ISBN
**GET** `/api/books?bibkeys=ISBN:0451526538&format=json&jscmd=data`

---

## Authentication

Authentication is required for write operations (saving data, adding notes, etc.). Open Library uses session cookies for authentication.

### Login
**Endpoint:** `POST /account/login`

**Parameters:**
- `username`: Your Open Library username
- `password`: Your Open Library password

#### Python Example
```python
import requests

session = requests.Session()
payload = {
    'username': 'your_username',
    'password': 'your_password'
}
response = session.post('https://openlibrary.org/account/login', data=payload)

if response.status_code == 200:
    print("Logged in successfully!")
else:
    print("Login failed.")
```

#### JavaScript Example (Node.js)
```javascript
const fetch = require('node-fetch');

async function login() {
    const response = await fetch('https://openlibrary.org/account/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            'username': 'your_username',
            'password': 'your_password'
        })
    });

    if (response.ok) {
        console.log("Logged in successfully!");
    } else {
        console.log("Login failed.");
    }
}
```

---

## Books API

Retrieve book data using Open Library IDs (OLIDs), ISBNs, or other identifiers.

### Get Book by OLID (JSON)
**GET** `/works/{OLID}.json` or `/books/{OLID}.json`

#### Python Snippet
```python
import requests

olid = "OL2747914W"
response = requests.get(f"https://openlibrary.org/works/{olid}.json")
book_data = response.json()
print(book_data.get('title'))
```

#### JavaScript Snippet
```javascript
async function getBook(olid) {
    const response = await fetch(`https://openlibrary.org/works/${olid}.json`);
    const data = await response.json();
    console.log(data.title);
}
```

---

## Authors API

Retrieve author details by their Open Library Author ID.

### Get Author Details
**GET** `/authors/{author_id}.json`

#### Python Snippet
```python
import requests

author_id = "OL26320A"
response = requests.get(f"https://openlibrary.org/authors/{author_id}.json")
author_data = response.json()
print(author_data.get('name'))
```

#### JavaScript Snippet
```javascript
async function getAuthor(authorId) {
    const response = await fetch(`https://openlibrary.org/authors/${authorId}.json`);
    const data = await response.json();
    console.log(data.name);
}
```

---

## Search API

Query the entire Open Library catalog.

### Search for Books
**GET** `/search.json?q={query}`

#### Python Snippet
```python
import requests

query = "the lord of the rings"
response = requests.get(f"https://openlibrary.org/search.json", params={'q': query})
results = response.json()
print(f"Found {results['numFound']} books.")
```

#### JavaScript Snippet
```javascript
async function searchBooks(query) {
    const response = await fetch(`https://openlibrary.org/search.json?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    console.log(`Found ${data.numFound} books.`);
}
```

---

## Covers API

Retrieve book covers in different sizes (S, M, L).

### Fetch Cover by ISBN
**URL:** `https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg`

Sizes: `S` (Small), `M` (Medium), `L` (Large)

#### Example
`https://covers.openlibrary.org/b/isbn/0385533225-L.jpg`

---

## Response Formats & Error Handling

- **JSON:** Most APIs return JSON. Use appropriate headers if needed (`Accept: application/json`).
- **Standard Status Codes:**
  - `200 OK`: Request successful.
  - `401 Unauthorized`: Authentication required or failed.
  - `404 Not Found`: The requested resource does not exist.
  - `500 Internal Server Error`: Something went wrong on the server.

### Error Handling Example (Python)
```python
try:
    response = requests.get("https://openlibrary.org/works/NON_EXISTENT.json")
    response.raise_for_status()
except requests.exceptions.HTTPError as err:
    print(f"HTTP error occurred: {err}")
```
