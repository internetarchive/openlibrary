---
phase: 03-code-examples
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/api/search.md
  - docs/api/books.md
  - docs/api/authors.md
  - docs/api/subjects.md
  - docs/api/covers.md
autonomous: true
requirements: [CODE-01, CODE-02, CODE-03, CODE-04]

must_haves:
  truths:
    - Developer can copy JavaScript/fetch example for any endpoint and run it successfully
    - Developer can copy Python example for any endpoint and run it successfully
    - Developer can use curl command-line examples to test any endpoint
    - All code examples are tested and verified to work with live API
  artifacts:
    - path: docs/api/search.md
      provides: JavaScript/fetch and Python code examples for Search API
      min_lines: 5
    - path: docs/api/books.md
      provides: JavaScript/fetch and Python code examples for Books API
      min_lines: 5
    - path: docs/api/authors.md
      provides: JavaScript/fetch and Python code examples for Authors API
      min_lines: 5
    - path: docs/api/subjects.md
      provides: JavaScript/fetch and Python code examples for Subjects API
      min_lines: 5
    - path: docs/api/covers.md
      provides: JavaScript/fetch and Python code examples for Covers API
      min_lines: 5
  key_links:
    - from: docs/api/search.md
      to: https://openlibrary.org/search.json
      via: fetch/python requests
    - from: docs/api/books.md
      to: https://openlibrary.org/works/OL27448W.json
      via: fetch/python requests
    - from: docs/api/authors.md
      to: https://openlibrary.org/authors/OL23919A.json
      via: fetch/python requests
    - from: docs/api/subjects.md
      to: https://openlibrary.org/subjects/love.json
      via: fetch/python requests
    - from: docs/api/covers.md
      to: https://covers.openlibrary.org/b/id/14625765-M.jpg
      via: img tag / Python PIL
---

<objective>
Add working JavaScript/fetch and Python code examples to all 5 API endpoint documentation files, and verify all examples work with the live API.

Purpose: Enable developers to copy working code examples in their preferred language and run them successfully.
Output: Updated docs with JS/Python examples + verification of all examples
</objective>

<execution_context>
@~\.config\opencode/get-shit-done/workflows\execute-plan.md
@~\.config\opencode\get-shit-done\templates\summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/02-api-reference/02-api-reference-01-SUMMARY.md
@docs/api/search.md
@docs/api/books.md
@docs/api/authors.md
@docs/api/subjects.md
@docs/api/covers.md
</context>

<tasks>

<task type="auto">
  <name>Add JavaScript/fetch code examples to all 5 endpoint docs</name>
  <files>
    docs/api/search.md
    docs/api/books.md
    docs/api/authors.md
    docs/api/subjects.md
    docs/api/covers.md
  </files>
  <action>
    Add a "Code Examples" section to each endpoint doc (or append to existing "Example Request" section) with JavaScript/fetch examples that:
    
    **For docs/api/search.md:**
    - Add JavaScript example using fetch that searches for "lord of the rings" with fields parameter
    - Must include proper User-Agent header via fetch option
    - Must handle response and log results
    
    **For docs/api/books.md:**
    - Add JavaScript example that fetches work by OLID (e.g., OL27448W)
    - Must include proper User-Agent header
    - Must handle response and log title/description
    
    **For docs/api/authors.md:**
    - Add JavaScript example that fetches author by OLID (e.g., OL23919A)
    - Must include proper User-Agent header
    - Must handle response and log name/bio
    
    **For docs/api/subjects.md:**
    - Add JavaScript example that fetches subject "love" with limit parameter
    - Must include proper User-Agent header
    - Must handle response and log work count/works
    
    **For docs/api/covers.md:**
    - Add JavaScript example showing how to construct cover URL and display image
    - Use cover_i from search results to construct URL
    
    Use consistent format:
    ```javascript
    // JavaScript (Node.js or browser fetch)
    async function fetchOpenLibrary() {
      const response = await fetch('https://openlibrary.org/search.json?q=lord+of+the+rings&limit=2', {
        headers: {
          'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'
        }
      });
      const data = await response.json();
      console.log(data);
    }
    ```
  </action>
  <verify>
    Run each JavaScript example with node to verify it executes without errors:
    node -e "const fetch = (...args) => import('node-fetch').then(({default: f}) => f(...args)); async function test() { const res = await fetch('https://openlibrary.org/search.json?q=test&limit=1', {headers:{'User-Agent':'Test/1.0'}}); console.log('Status:', res.status); }; test()"
  </verify>
  <done>
    All 5 endpoint docs have JavaScript/fetch examples that can be copied and run successfully
  </done>
</task>

<task type="auto">
  <name>Add Python code examples to all 5 endpoint docs</name>
  <files>
    docs/api/search.md
    docs/api/books.md
    docs/api/authors.md
    docs/api/subjects.md
    docs/api/covers.md
  </files>
  <action>
    Add Python code examples to each endpoint doc using the requests library:
    
    **For docs/api/search.md:**
    - Add Python example using requests that searches for "lord of the rings" with fields parameter
    - Must include proper User-Agent header
    - Must handle response and print results
    
    **For docs/api/books.md:**
    - Add Python example that fetches work by OLID (e.g., OL27448W)
    - Must include proper User-Agent header
    - Must handle response and print title/description
    
    **For docs/api/authors.md:**
    - Add Python example that fetches author by OLID (e.g., OL23919A)
    - Must include proper User-Agent header
    - Must handle response and print name/bio
    
    **For docs/api/subjects.md:**
    - Add Python example that fetches subject "love" with limit parameter
    - Must include proper User-Agent header
    - Must handle response and print work count/works
    
    **For docs/api/covers.md:**
    - Add Python example showing how to download cover image using requests and save to file
    
    Use consistent format:
    ```python
    import requests
    
    def fetch_openlibrary():
        url = 'https://openlibrary.org/search.json'
        params = {'q': 'lord of the rings', 'limit': 2}
        headers = {'User-Agent': 'MyApp/1.0 (https://myapp.com; contact@myapp.com)'}
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        print(data)
    ```
  </action>
  <verify>
    Run Python examples to verify they work:
    python -c "import requests; r = requests.get('https://openlibrary.org/search.json?q=test&limit=1', headers={'User-Agent':'Test/1.0'}); print('Status:', r.status_code)"
  </verify>
  <done>
    All 5 endpoint docs have Python examples that can be copied and run successfully
  </done>
</task>

<task type="auto">
  <name>Verify all code examples work with live API</name>
  <files>
    docs/api/search.md
    docs/api/books.md
    docs/api/authors.md
    docs/api/subjects.md
    docs/api/covers.md
  </files>
  <action>
    Test all code examples (JavaScript and Python) to verify they work with the live Open Library API:
    
    1. For each endpoint doc, extract the code examples
    2. Run JavaScript examples with Node.js (or verify syntax is correct)
    3. Run Python examples and verify they execute successfully
    4. Verify curl examples still work (they existed before)
    5. Check that responses contain expected data (not errors)
    
    Test specifically:
    - Search API: returns docs array with expected fields
    - Books API: returns work with title field
    - Authors API: returns author with name field
    - Subjects API: returns works array with work_count
    - Covers API: image URL is valid and accessible
    
    Fix any examples that don't work correctly.
  </action>
  <verify>
    Execute each example type and confirm HTTP 200:
    - curl: curl -s -o /dev/null -w "%{http_code}" -H "User-Agent: Test/1.0" "https://openlibrary.org/search.json?q=test&limit=1"
    - Python: python -c "import requests; r = requests.get('https://openlibrary.org/search.json?q=test&limit=1', headers={'User-Agent':'Test/1.0'}); print('Search:', r.status_code)"
    - Python: python -c "import requests; r = requests.get('https://openlibrary.org/works/OL27448W.json', headers={'User-Agent':'Test/1.0'}); print('Books:', r.status_code)"
    - Python: python -c "import requests; r = requests.get('https://openlibrary.org/authors/OL23919A.json', headers={'User-Agent':'Test/1.0'}); print('Authors:', r.status_code)"
    - Python: python -c "import requests; r = requests.get('https://openlibrary.org/subjects/love.json?limit=1', headers={'User-Agent':'Test/1.0'}); print('Subjects:', r.status_code)"
  </verify>
  <done>
    All code examples in all 5 endpoint docs are verified to work with live API (HTTP 200 responses with valid data)
  </done>
</task>

</tasks>

<verification>
1. Check each doc has both JavaScript and Python examples
2. Run each example and verify HTTP 200 status
3. Verify response contains expected fields
4. Confirm curl examples still present and working
</verification>

<success_criteria>

- Developer can copy JavaScript/fetch example for any endpoint and run it successfully
- Developer can copy Python example for any endpoint and run it successfully
- Developer can use curl command-line examples to test any endpoint
- All code examples are tested and verified to work with live API
  </success_criteria>

<output>
After completion, create `.planning/phases/03-code-examples/03-code-examples-01-SUMMARY.md`
</output>
