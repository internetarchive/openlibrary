# Covers API

> The Covers API provides access to book cover images in various sizes.

## Overview

The Covers API is different from other Open Library APIs - it returns **images** (JPEG), not JSON data. The API provides cover images for books, authors, and subjects.

## Base URL

```
https://covers.openlibrary.org
```

## Cover Types

### Book Covers

```
https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg
https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg
https://covers.openlibrary.org/b/olid/{olid}-{size}.jpg
https://covers.openlibrary.org/b/oclc/{oclc}-{size}.jpg
https://covers.openlibrary.org/b/lccn/{lccn}-{size}.jpg
```

### Author Photos

```
https://covers.openlibrary.org/a/olid/{olid}-{size}.jpg
```

### Subject Images

```
https://covers.openlibrary.org/s/subject/{subject_name}-{size}.jpg
```

## Size Options

| Size | Dimensions | Use Case                   |
| ---- | ---------- | -------------------------- |
| `S`  | 90×135 px  | Thumbnails, lists          |
| `M`  | 200×300 px | Standard display           |
| `L`  | 400×600 px | Large display, detail view |

> **Note:** Larger sizes are not always available. The API will return the largest available size if the requested size doesn't exist.

## Path Parameters

### Book Covers

| Parameter | Type           | Required | Description                                       |
| --------- | -------------- | -------- | ------------------------------------------------- |
| `id`      | integer/string | Yes      | Cover ID (from search), ISBN, OLID, OCLC, or LCCN |
| `size`    | string         | No       | Size: `S`, `M`, or `L` (default: `M`)             |

### Author Photos

| Parameter | Type   | Required | Description                           |
| --------- | ------ | -------- | ------------------------------------- |
| `olid`    | string | Yes      | Author OLID (e.g., `OL23919A`)        |
| `size`    | string | No       | Size: `S`, `M`, or `L` (default: `M`) |

## Cover ID from Search

The easiest way to get covers is to:

1. Use the [Search API](./search.md) to find books
2. Extract the `cover_i` field from search results
3. Use that ID with the Covers API

### Example: Get Cover from Search

```bash
curl "https://openlibrary.org/search.json?q=lord+of+the+rings&limit=1&fields=key,title,cover_i"
```

Response:

```json
{
  "docs": [
    {
      "key": "/works/OL27448W",
      "title": "The Lord of the Rings",
      "cover_i": 14625765
    }
  ]
}
```

Now use `14625765` for the cover:

```
https://covers.openlibrary.org/b/id/14625765-M.jpg
```

## Examples

### By Cover ID (from search)

```
https://covers.openlibrary.org/b/id/14625765-S.jpg  # Small
https://covers.openlibrary.org/b/id/14625765-M.jpg  # Medium
https://covers.openlibrary.org/b/id/14625765-L.jpg  # Large
```

### By ISBN

```
https://covers.openlibrary.org/b/isbn/0451526934-M.jpg
https://covers.openlibrary.org/b/isbn/978-0451526939-M.jpg
```

### By OLID

```
https://covers.openlibrary.org/b/olid/OL27448W-M.jpg
```

### By Author OLID

```
https://covers.openlibrary.org/a/olid/OL23919A-M.jpg
```

## HTTP Response Codes

| Code | Description                                              |
| ---- | -------------------------------------------------------- |
| 200  | Success - image returned                                 |
| 302  | Redirect to default cover (requested size not available) |
| 404  | Cover not found                                          |

## Handling Missing Covers

When a cover is not available, the API returns a 302 redirect to a default cover placeholder. Your application should handle this:

```javascript
// Example: Handle missing covers
async function getCoverUrl(coverId, size = "M") {
  const response = await fetch(
    `https://covers.openlibrary.org/b/id/${coverId}-${size}.jpg`,
    { method: "HEAD" },
  );

  if (response.ok) {
    return response.url;
  }
  // Return null or a default placeholder URL
  return null;
}
```

## Image URLs vs JSON API

It's important to understand:

- **This API returns images directly** - not JSON
- Use the URLs directly in `<img>` tags or download them
- The URLs can be cached and embedded in HTML

### Example: HTML Image Tag

```html
<img
  src="https://covers.openlibrary.org/b/id/14625765-M.jpg"
  alt="The Lord of the Rings cover"
  loading="lazy"
/>
```

### Example: Python

```python
from IPython.display import Image, display

# Display cover in notebook
display(Image(url="https://covers.openlibrary.org/b/id/14625765-M.jpg"))
```

## Best Practices

### 1. Use the Right Size

| Use Case       | Recommended Size |
| -------------- | ---------------- |
| Search results | `S`              |
| Book lists     | `M`              |
| Detail pages   | `L`              |

### 2. Lazy Loading

Always use `loading="lazy"` for images below the fold:

```html
<img src="..." loading="lazy" alt="..." />
```

### 3. Fallbacks

Have a placeholder for missing covers:

```html
<img
  src="https://covers.openlibrary.org/b/id/14625765-M.jpg"
  onerror="this.src='/images/book-placeholder.png'"
  alt="Book title"
/>
```

### 4. Cache Responsibly

The covers API supports long-term caching:

- Check the `Cache-Control` header
- Use proper `ETag` headers for conditional requests

```bash
curl -sI "https://covers.openlibrary.org/b/id/14625765-M.jpg" | grep -i "cache\|etag"
```

Response:

```
Cache-Control: public
ETag: "14625765-m"
Expires: Sat, 09 Feb 2126 02:15:19 GMT
```

## Technical Details

- **Format:** JPEG
- **Host:** `covers.openlibrary.org` (separate from the main API)
- **CORS:** Enabled - images can be loaded from any origin
- **Rate Limits:** No explicit rate limit, but be respectful
- **Authentication:** Not required for fetching images

## Quick Reference

| Resource      | URL Pattern                    |
| ------------- | ------------------------------ |
| Cover by ID   | `/b/id/{id}-{size}.jpg`        |
| Cover by ISBN | `/b/isbn/{isbn}-{size}.jpg`    |
| Cover by OLID | `/b/olid/{olid}-{size}.jpg`    |
| Author photo  | `/a/olid/{olid}-{size}.jpg`    |
| Subject image | `/s/subject/{name}-{size}.jpg` |

## Related Endpoints

- [Search API](./search.md) - Get `cover_i` for books
- [Books API](./books.md) - Get `covers` array for works
- [Authors API](./authors.md) - Get `photos` for authors
- [Subjects API](./subjects.md) - Get `cover_id` for subject works
