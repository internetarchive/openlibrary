# Error Handling & Troubleshooting

When interacting with the Open Library API, your application should be prepared to handle various HTTP response codes. This guide explains common error codes, rate limiting policies, and how to implement robust error handling.

## HTTP Error Codes

Open Library uses standard HTTP status codes to indicate the success or failure of an API request.

| Status Code | Name                  | Meaning in Open Library                                                      | Recommended Action                                                                                                       |
| :---------- | :-------------------- | :--------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| `200`       | OK                    | The request was successful.                                                  | Process the response data.                                                                                               |
| `400`       | Bad Request           | The request was invalid or could not be understood by the server.            | Check your query parameters and request format.                                                                          |
| `403`       | Forbidden             | Access is denied, typically due to a missing or generic `User-Agent` header. | [Identify your application](./authentication.md) with a proper User-Agent header.                                        |
| `404`       | Not Found             | The requested resource (book, author, etc.) does not exist.                  | Verify the ID or URL. Note that some valid IDs might not have JSON representations yet.                                  |
| `429`       | Too Many Requests     | You have exceeded the rate limit.                                            | Stop making requests immediately and implement [exponential backoff](#exponential-backoff).                              |
| `500`       | Internal Server Error | Something went wrong on Open Library's end.                                  | Wait a few minutes and try again. If it persists, check the [Open Library Status](https://openlibrary.org/dev/docs/api). |
| `503`       | Service Unavailable   | The server is currently overloaded or down for maintenance.                  | Retry after a delay.                                                                                                     |

---

## Rate Limiting

Open Library is a free, public resource. To ensure availability for everyone, we apply rate limits to all API requests.

### Identification is Key

Rate limits are primarily tracked by your **IP address** and your **User-Agent header**.

- **Anonymous requests** (missing or generic User-Agent) are heavily throttled or blocked.
- **Identified requests** (unique User-Agent with contact info) receive more generous limits and better stability.

### Best Practices to Avoid Rate Limits

1. **Include a User-Agent**: Always identify your app: `MyApp/1.0 (https://myapp.com; contact@myapp.com)`.
2. **Cache Results**: Store API responses locally (e.g., in Redis or a database) if you need to access the same data multiple times.
3. **Avoid Sequential Requests**: Don't fetch 100 books one after another in a tight loop.
4. **Use Bulk Endpoints**: If you need multiple records, check if the endpoint supports multiple IDs (e.g., the [Books API](./reference/books.md) supports multiple BIBKEYS).
5. **Be Reasonable**: Limit your requests to around 1-2 per second for sustained usage.

---

## Exponential Backoff

If your application receives a `429 Too Many Requests` response, you **must** stop making requests and wait before retrying. **Exponential backoff** is the standard way to handle this: you increase the wait time after each failed attempt.

### Implementation Example (JavaScript)

```javascript
async function fetchWithRetry(url, options = {}, maxRetries = 5) {
  let retries = 0;
  let backoff = 1000; // Start with 1 second

  while (retries < maxRetries) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          "User-Agent": "MyApp/1.0 (https://myapp.com; contact@myapp.com)",
          ...options.headers,
        },
      });

      if (response.status === 429) {
        console.warn(`Rate limited (429). Retrying in ${backoff}ms...`);
        await new Promise((resolve) => setTimeout(resolve, backoff));
        retries++;
        backoff *= 2; // Exponentially increase wait time
        continue;
      }

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      if (retries >= maxRetries - 1) throw error;
      retries++;
      await new Promise((resolve) => setTimeout(resolve, backoff));
      backoff *= 2;
    }
  }
}
```

### Implementation Example (Python)

```python
import requests
import time

def fetch_with_retry(url, params=None, max_retries=5):
    retries = 0
    backoff = 1  # Start with 1 second
    headers = {'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'}

    while retries < max_retries:
        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 429:
            print(f"Rate limited (429). Retrying in {backoff}s...")
            time.sleep(backoff)
            retries += 1
            backoff *= 2  # Exponentially increase wait time
            continue

        response.raise_for_status()
        return response.json()

    raise Exception("Max retries exceeded")
```

---

## Troubleshooting Common Issues

### "Why am I getting 403 Forbidden?"

This almost always means you are missing a `User-Agent` header, or your User-Agent is being blocked (e.g., using a generic one like "python-requests/2.25.1"). See the [Authentication Guide](./authentication.md) for the correct format.

### "Why are my search results inconsistent?"

The search index is updated frequently. If you perform the same search twice within a few seconds, you might hit different backend nodes that are slightly out of sync, or the index may have been updated between requests.

### "The JSON response is missing fields I expect."

Open Library data is crowdsourced and may be incomplete. Not every book has a description, cover, or author ID. Always write your code defensively to handle missing fields (e.g., use `data.get('description')` in Python or `data?.description` in JS).

### "I'm getting a 404 for a book I know exists."

Check if you are appending `.json` correctly to the URL (e.g., `/books/OL12345W.json`). Also, ensure you are using the correct ID type (Work ID vs. Edition ID).
