---
phase: 02-api-reference
plan: 01
type: execute
wave: 1
depends_on: [01-quickstart-01]
files_modified:
  [
    docs/api/search.md,
    docs/api/books.md,
    docs/api/authors.md,
    docs/api/subjects.md,
    docs/api/covers.md,
  ]
autonomous: true
requirements: [REF-01, REF-02, REF-03, REF-04, REF-05, SCH-01, SCH-02, SCH-03]

must_haves:
  truths:
    - "Developer can find documentation for every major endpoint (search, books, authors, subjects, covers)"
    - "Developer can understand response structure for each endpoint (field types, nullability)"
    - "Developer has example responses for every endpoint"
  artifacts:
    - path: "docs/api/search.md"
      provides: "Search API endpoint documentation with response schema and examples"
    - path: "docs/api/books.md"
      provides: "Books API endpoint documentation with response schema and examples"
    - path: "docs/api/authors.md"
      provides: "Authors API endpoint documentation with response schema and examples"
    - path: "docs/api/subjects.md"
      provides: "Subjects API endpoint documentation with response schema and examples"
    - path: "docs/api/covers.md"
      provides: "Covers API endpoint documentation with response schema and examples"
  key_links:
    - from: "docs/api/search.md"
      to: "docs/api/authentication.md"
      via: "User-Agent requirement reference"
    - from: "docs/api/books.md"
      to: "docs/api/authentication.md"
      via: "User-Agent requirement reference"
    - from: "docs/api/authors.md"
      to: "docs/api/authentication.md"
      via: "User-Agent requirement reference"
    - from: "docs/api/subjects.md"
      to: "docs/api/authentication.md"
      via: "User-Agent requirement reference"
    - from: "docs/api/covers.md"
      to: "docs/api/authentication.md"
      via: "User-Agent requirement reference"
---

<objective>
Document all major Open Library API endpoints with complete response schemas and examples

Purpose: Enable developers to understand each endpoint's request format, response structure, and see real example responses

Output: 5 API reference documents (search, books, authors, subjects, covers)
</objective>

<execution_context>
@~\docs\api\getting-started.md
@~\docs\api\authentication.md
</execution_context>

<context>
@.planning\phases\01-quickstart\01-quickstart-01-SUMMARY.md
@.planning\ROADMAP.md
@.planning\REQUIREMENTS.md
</context>

<tasks>

<task type="auto">
  <name>Document Search API endpoint</name>
  <files>docs/api/search.md</files>
  <action>
Create docs/api/search.md with:
- Endpoint: GET /search.json
- Query parameters: q, title, author, subject, isbn, limit, offset, fields, etc.
- Full response schema with field types, nullability, descriptions
- Example request and full example response (real API call)
- Link to authentication.md for User-Agent requirement
- Use consistent format from getting-started.md (tables for parameters, code blocks for examples)
  </action>
  <verify>curl -s "https://openlibrary.org/search.json?q=the+lord+of+the+rings&limit=1" | head -c 500 returns valid JSON</verify>
  <done>Search API documentation includes all query parameters, full response schema with types/nullability, and real example response</done>
</task>

<task type="auto">
  <name>Document Books API endpoint</name>
  <files>docs/api/books.md</files>
  <action>
Create docs/api/books.md with:
- Endpoint: GET /books/{id} (works and editions)
- Path parameters: id (OLID, ISBN, LCCN)
- Response schema with all fields (title, authors, subjects, publishers, etc.)
- Full example response from real API call
- Explain difference between /works/ and /books/ endpoints
- Link to authentication.md for User-Agent requirement
  </action>
  <verify>curl -s "https://openlibrary.org/works/OL27448W.json" | head -c 500 returns valid JSON</verify>
  <done>Books API documentation includes path parameters, full response schema with types/nullability, and real example response</done>
</task>

<task type="auto">
  <name>Document Authors API endpoint</name>
  <files>docs/api/authors.md</files>
  <action>
Create docs/api/authors.md with:
- Endpoint: GET /authors/{id}
- Path parameters: id (OLID)
- Response schema with all fields (name, bio, birth_date, death_date, photos, etc.)
- Full example response from real API call
- Include /authors/{id}/works.json for author works
- Link to authentication.md for User-Agent requirement
  </action>
  <verify>curl -s "https://openlibrary.org/authors/OL23919A.json" | head -c 500 returns valid JSON</verify>
  <done>Authors API documentation includes path parameters, full response schema with types/nullability, and real example response</done>
</task>

<task type="auto">
  <name>Document Subjects API endpoint</name>
  <files>docs/api/subjects.md</files>
  <action>
Create docs/api/subjects.md with:
- Endpoint: GET /subjects/{name}
- Path parameters: name (subject name, URL-encoded)
- Query parameters: limit, offset
- Response schema with all fields (name, work_count, works array, etc.)
- Full example response from real API call
- Explain subject name URL encoding (spaces to underscores)
- Link to authentication.md for User-Agent requirement
  </action>
  <verify>curl -s "https://openlibrary.org/subjects/love.json?limit=1" | head -c 500 returns valid JSON</verify>
  <done>Subjects API documentation includes path parameters, full response schema with types/nullability, and real example response</done>
</task>

<task type="auto">
  <name>Document Covers API endpoint</name>
  <files>docs/api/covers.md</files>
  <action>
Create docs/api/covers.md with:
- Endpoint: GET /covers/{id} and covers.openlibrary.org URLs
- Path parameters: id (cover_i from search, ISBN, OCLC, LCCN)
- Query parameters: size (S, M, L)
- Cover URL construction examples
- Explain different cover sizes and when to use each
- Note: Covers API returns images, not JSON - document URL structure
- Link to authentication.md for User-Agent requirement when fetching metadata
  </action>
  <verify>curl -sI "https://covers.openlibrary.org/b/id/14625765-M.jpg" | head -5 returns HTTP 200</verify>
  <done>Covers API documentation includes URL construction, size parameters, and practical usage examples</done>
</task>

</tasks>

<verification>
Each endpoint doc verified by:
1. Making actual API call and confirming JSON response
2. Checking all documented fields appear in real response
3. Verifying code examples include User-Agent header
</verification>

<success_criteria>

1. Developer can find documentation for every major endpoint (search, books, authors, subjects, covers) - 5 docs exist in docs/api/
2. Developer can understand response structure for each endpoint - each doc has schema table with types/nullability
3. Developer has example responses for every endpoint - each doc has real JSON examples from live API
   </success_criteria>

<output>
After completion, create `.planning/phases/02-api-reference/02-api-reference-01-SUMMARY.md`
</output>
