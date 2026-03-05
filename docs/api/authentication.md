# Authentication Guide

> **⚠️ IMPORTANT: User-Agent Header Required**
>
> The Open Library API requires a `User-Agent` header on all requests. Requests without a proper User-Agent may be blocked or rate-limited.

## Why User-Agent is Required

The `User-Agent` header serves several important purposes:

1. **Application Identification** — Open Library can identify which application is making requests
2. **Rate Limiting** — Helps Open Library track usage and apply fair limits per application
3. **Contact for Issues** — If your application causes problems, Open Library can reach out to help
4. **Community Respect** — Shows you're a responsible API consumer

Without a User-Agent, your requests may be throttled or rejected.

## User-Agent Format

We recommend including three pieces of information:

```
ApplicationName/Version (URL; contact@email.com)
```

**Example:**

```
MyApp/1.0 (https://myapp.com; contact@myapp.com)
```

### Best Practices

Your User-Agent should include:

| Component     | Example             | Purpose                          |
| ------------- | ------------------- | -------------------------------- |
| App name      | `MyApp`             | Identifies your application      |
| Version       | `1.0`               | Helps track different versions   |
| Homepage URL  | `https://myapp.com` | Link to your project             |
| Contact email | `contact@myapp.com` | Allows Open Library to reach you |

## Code Examples

### curl

```bash
curl -A "MyApp/1.0 (https://myapp.com; contact@myapp.com)" \
  "https://openlibrary.org/search.json?q=python"
```

Or using the `-H` flag:

```bash
curl -H "User-Agent: MyApp/1.0 (https://myapp.com; contact@myapp.com)" \
  "https://openlibrary.org/search.json?q=python"
```

### JavaScript (fetch)

```javascript
const response = await fetch("https://openlibrary.org/search.json?q=python", {
  headers: {
    "User-Agent": "MyApp/1.0 (https://myapp.com; contact@myapp.com)",
  },
});
const data = await response.json();
```

### JavaScript (axios)

```javascript
const axios = require("axios");

const response = await axios.get("https://openlibrary.org/search.json", {
  params: { q: "python" },
  headers: {
    "User-Agent": "MyApp/1.0 (https://myapp.com; contact@myapp.com)",
  },
});
console.log(response.data);
```

### Python (requests)

```python
import requests

response = requests.get(
    'https://openlibrary.org/search.json',
    params={'q': 'python'},
    headers={'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'}
)
data = response.json()
print(data)
```

### Python (urllib)

```python
import urllib.request
import urllib.parse

url = 'https://openlibrary.org/search.json?' + urllib.parse.urlencode({'q': 'python'})
request = urllib.request.Request(
    url,
    headers={'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'}
)
response = urllib.request.urlopen(request)
data = response.read()
```

### Ruby

```ruby
require 'net/http'
require 'uri'

uri = URI.parse('https://openlibrary.org/search.json?q=python')
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = true

request = Net::HTTP::Get.new(uri)
request['User-Agent'] = 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'

response = http.request(request)
puts response.body
```

### Go

```go
package main

import (
    "fmt"
    "io/ioutil"
    "net/http"
)

func main() {
    client := &http.Client{}
    req, _ := http.NewRequest("GET", "https://openlibrary.org/search.json?q=python", nil)
    req.Header.Set("User-Agent", "MyApp/1.0 (https://myapp.com; contact@myapp.com)")

    resp, _ := client.Do(req)
    defer resp.Body.Close()
    body, _ := ioutil.ReadAll(resp.Body)
    fmt.Println(string(body))
}
```

### PHP

```php
<?php
$ch = curl_init('https://openlibrary.org/search.json?q=python');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'User-Agent: MyApp/1.0 (https://myapp.com; contact@myapp.com)'
]);
$response = curl_exec($ch);
curl_close($ch);
$data = json_decode($response, true);
print_r($data);
?>
```

## Common Mistakes to Avoid

### ❌ Bad User-Agent Strings

```bash
# Missing or empty User-Agent
curl "https://openlibrary.org/search.json?q=test"

# Generic browser User-Agent (may be blocked)
curl -A "Mozilla/5.0" "https://openlibrary.org/search.json?q=test"

# Just a single word (not helpful)
curl -H "User-Agent: MyApp" "https://openlibrary.org/search.json"
```

### ✅ Good User-Agent Strings

```bash
# Complete with all recommended parts
curl -H "User-Agent: MyBookApp/2.0 (https://mybookapp.example.com; hello@mybookapp.example.com)" \
  "https://openlibrary.org/search.json?q=python"

# Minimum acceptable
curl -H "User-Agent: MyApp/1.0" "https://openlibrary.org/search.json?q=python"
```

## Rate Limiting

Open Library uses the User-Agent to track request rates. To be a good API citizen:

1. **Include User-Agent** — Always identify your application
2. **Be reasonable** — Don't make thousands of requests per minute
3. **Cache results** — Store data you reuse instead of re-fetching
4. **Handle 429 errors** — If you get rate limited, wait and retry with backoff

See the [Error Handling Guide](./error-handling.md) for handling rate limits.

## Summary

| Requirement        | Value                                              |
| ------------------ | -------------------------------------------------- |
| Header Name        | `User-Agent`                                       |
| Required           | Yes                                                |
| Recommended Format | `AppName/Version (URL; email)`                     |
| Example            | `MyApp/1.0 (https://myapp.com; contact@myapp.com)` |

Always include a descriptive User-Agent header in your API requests!
