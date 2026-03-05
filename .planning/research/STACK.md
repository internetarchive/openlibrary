# Stack Research: API Documentation Tools

**Domain:** Developer API Documentation
**Researched:** 2026-03-04
**Confidence:** HIGH

## Executive Recommendation

For Open Library's API documentation project, the recommended approach combines **OpenAPI specification as the source of truth** with **Docusaurus** for hosting, supplemented by **Stripe-like explanatory guides**. This provides:

- Automated sync between API and docs
- Full control over styling and hosting
- Industry-standard format for AI/agent consumption
- Zero licensing costs

---

## Recommended Stack

### Core Technologies

| Technology                         | Version | Purpose                      | Why Recommended                                                                                                                                        |
| ---------------------------------- | ------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **OpenAPI 3.x**                    | 3.1.0   | API specification format     | Industry standard, machine-readable, enables auto-generation of reference docs and AI agent consumption. 90%+ of major APIs use it as source of truth. |
| **Docusaurus**                     | 3.x     | Documentation site generator | MIT open-source, powers React Native/Supabase/Figma docs, full hosting control, docs-as-code workflow matches Open Library's Python/JS stack           |
| **docusaurus-plugin-openapi-docs** | latest  | OpenAPI to MDX conversion    | Palo Alto Networks-maintained, converts OpenAPI specs to Docusaurus pages automatically, supports interactive demos                                    |

### Documentation Structure

| Component       | Purpose                             | Tool/Format                              |
| --------------- | ----------------------------------- | ---------------------------------------- |
| API Reference   | Auto-generated endpoint docs        | OpenAPI → docusaurus-plugin-openapi-docs |
| Getting Started | Quickstart guide for new developers | Custom MDX pages                         |
| Authentication  | User-Agent, rate limits, keys       | Custom MDX with examples                 |
| Code Examples   | curl, Python, JavaScript            | Embedded in guides + auto-generated      |
| Troubleshooting | Common errors and solutions         | Custom MDX pages                         |

### Supporting Libraries

| Library         | Version | Purpose                        | When to Use                              |
| --------------- | ------- | ------------------------------ | ---------------------------------------- |
| **Swagger UI**  | 5.x     | Interactive API explorer       | Embedding "try it" functionality in docs |
| **Redoc**       | 3.x     | Alternative reference renderer | If Docusaurus approach proves complex    |
| **prism-media** | latest  | Syntax highlighting            | Code block styling in Docusaurus         |

### Hosting Options

| Platform         | Free Tier           | Notes                             |
| ---------------- | ------------------- | --------------------------------- |
| Vercel           | 100GB bandwidth     | Zero-config Docusaurus deployment |
| Netlify          | 100GB bandwidth     | Good free tier, drag-drop deploy  |
| Cloudflare Pages | Unlimited bandwidth | Best for cost, 20k file limit     |
| GitHub Pages     | Unlimited           | Native Docusaurus support         |

---

## Alternatives Considered

| Recommended          | Alternative | When to Use Alternative                                                           |
| -------------------- | ----------- | --------------------------------------------------------------------------------- |
| Docusaurus + OpenAPI | Mintlify    | If budget ($300/mo) acceptable and team prefers managed solution over self-hosted |
| Docusaurus + OpenAPI | GitBook     | If non-technical contributors need visual editor                                  |
| Docusaurus + OpenAPI | Redocly     | If only need reference docs (no guides/tutorials) and have enterprise budget      |

### Why Not Mintlify/GitBook/Redocly (SaaS)

| Tool     | Problem                                | Why It Matters                                              |
| -------- | -------------------------------------- | ----------------------------------------------------------- |
| Mintlify | $300/mo minimum                        | Overkill for docs-only project without SDK generation needs |
| GitBook  | Price increased 2-3x recently          | Now $65-249/mo base + per-user costs                        |
| Redocly  | No self-hosted option for Pro features | Need to pay for interactive playground                      |
| All SaaS | Vendor lock-in                         | Open Library benefits from full control                     |

---

## What NOT to Use

| Avoid                                       | Why                                                              | Use Instead             |
| ------------------------------------------- | ---------------------------------------------------------------- | ----------------------- |
| **Wiki-style docs** (MediaWiki, Confluence) | Poor developer experience, no code highlighting, hard to version | Docusaurus (MDX-based)  |
| **PDF documentation**                       | Not searchable, poor mobile experience, hard to update           | Web-based (Docusaurus)  |
| **Swagger Editor alone**                    | Only generates reference, no explanatory content                 | OpenAPI + Docusaurus    |
| **Manual docs only**                        | Documentation drift, high maintenance                            | OpenAPI auto-generation |
| **Postman for docs**                        | No public-facing docs, designed for internal API testing         | Docusaurus or Mintlify  |

---

## OpenAPI Implementation for Open Library

### Required OpenAPI Fields

```yaml
openapi: 3.1.0
info:
  title: Open Library API
  version: 1.0.0
  description: Public APIs for accessing Open Library data
servers:
  - url: https://openlibrary.org
    description: Production
paths:
  /search.json:
    get:
      summary: Search books
      parameters:
        - name: q
          in: query
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
      responses:
        "200":
          description: Search results
          content:
            application/json:
              schema:
                type: object
```

### Essential Documentation Sections

| Section         | Content                            | Priority |
| --------------- | ---------------------------------- | -------- |
| Getting Started | Quick intro, base URL, rate limits | Required |
| Authentication  | User-Agent requirement, policy     | Required |
| Search API      | Query parameters, response format  | Required |
| Books API       | Get by ISBN, OCLC, LCCN            | Required |
| Authors API     | Get author details, works          | Required |
| Subjects API    | Browse by subject                  | Required |
| Rate Limits     | Requests per second/day, headers   | Required |
| Error Handling  | Error codes, messages              | Required |
| Code Examples   | curl, Python, JavaScript           | Required |
| Troubleshooting | Common issues                      | Required |

---

## Installation & Setup

```bash
# Install Docusaurus
npx create-docusaurus@latest openlibrary-docs classic

# Install OpenAPI plugin
cd openlibrary-docs
npm install docusaurus-plugin-openapi-docs

# Configure in docusaurus.config.js
plugins: [
  [
    'docusaurus-plugin-openapi-docs',
    {
      docsPluginId: 'classic',
      config: {
        openlib: {
          specPath: 'openapi.yaml',
          outputDir: 'docs/api',
        },
      },
    },
  ],
]
```

---

## Stack Patterns by Context

**If Open Library backend is modifiable:**

- Add OpenAPI annotations to Python code using `flask-smorest` or ` connexion`
- Auto-generate spec from code annotations
- Benefit: Docs always in sync with implementation

**If Open Library backend is NOT modifiable (docs project only):**

- Manually create OpenAPI spec from existing API behavior
- Use response examples from real API calls
- Benefit: Can document existing APIs without backend changes

**If team has React experience:**

- Use Docusaurus with custom React components for interactive examples
- Add custom "copy to clipboard", language switcher

**If team prefers simplicity:**

- Start with static MDX pages, add OpenAPI incrementally
- Use Swagger UI for interactive playground
- Migrate to full Docusaurus when needed

---

## Version Compatibility

| Package                        | Compatible With      | Notes                        |
| ------------------------------ | -------------------- | ---------------------------- |
| Docusaurus 3.x                 | Node 18+             | Current stable               |
| docusaurus-plugin-openapi-docs | Docusaurus 3.x       | Check compatibility matrix   |
| OpenAPI 3.1.0                  | All major generators | Backward compatible with 3.0 |
| Swagger UI 5.x                 | OpenAPI 3.x          | Supports 3.1                 |

---

## Sources

- [Ferndesk: Best API Documentation Tools 2026](https://ferndesk.com/blog/best-api-documentation-tools) — HIGH confidence, Dec 2025, comprehensive comparison
- [Dev.to: Ultimate Guide to API Documentation Tools 2026](https://dev.to/therealmrmumba/the-ultimate-guide-to-api-documentation-tools-for-2026-2f7m) — HIGH confidence, Feb 2026
- [OneUptime: OpenAPI Documentation Guide](https://oneuptime.com/blog/post/2026-01-27-openapi-documentation/view) — HIGH confidence, Jan 2026
- [Fern: API Documentation Best Practices Guide](https://buildwithfern.com/post/api-documentation-best-practices-guide) — HIGH confidence, Feb 2026
- [OpenAPI Initiative](https://spec.openapis.org/) — Official spec, authoritative
- [Docusaurus GitHub](https://github.com/facebook/docusaurus) — 61.8k stars, Meta-maintained

---

_Stack research for: Open Library API Documentation_
_Researched: 2026-03-04_
