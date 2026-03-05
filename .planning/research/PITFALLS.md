# Pitfalls Research

**Domain:** API Documentation
**Researched:** 2026-03-04
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Non-Working Code Examples

**What goes wrong:**
Code examples in documentation are outdated, contain syntax errors, or fail when copy-pasted. Developers spend hours debugging examples that should work out of the box.

**Why it happens:**
Examples are written once and never validated against current API behavior. When API changes, examples drift. No automated testing of documentation examples.

**How to avoid:**

- Test every code example manually before publishing
- Include expected response alongside each request example
- Use modern syntax (async/await, not callbacks)
- Provide multiple languages (at minimum: JavaScript, Python)
- Mark examples with last-validated date
- Set up automated CI that makes actual API calls from docs

**Warning signs:**

- Examples reference deprecated SDK versions
- Syntax errors visible in code blocks
- "TODO: add example" comments still present
- Response data shown differs from actual API response

**Phase to address:**
Documentation Implementation - Each endpoint's examples must be tested

---

### Pitfall 2: Missing or Vague Error Documentation

**What goes wrong:**
When API calls fail, developers receive cryptic error messages with no explanation. Docs either omit error handling entirely or say "returns an error response" without specifics.

**Why it happens:**
Error handling considered "obvious" or low priority. Errors seen as edge cases rather than expected behavior developers must handle.

**How to avoid:**

- Document every possible error code/response
- Include HTTP status code meaning (400, 401, 429, 500, etc.)
- Show example error response for each error type
- Explain what triggers each error and how to fix it
- Cover rate limit errors explicitly (429 responses)

**Warning signs:**

- Error section says "see API for error responses"
- No mention of rate limiting errors
- Error codes listed without descriptions

**Phase to address:**
Documentation Implementation - Error handling section for each endpoint

---

### Pitfall 3: Authentication Confusion

**What goes wrong:**
Developers cannot figure out how to authenticate. Required headers not documented clearly. Applications get blocked or rate-limited because they don't know about User-Agent requirements.

**Why it happens:**
Authentication assumed to be obvious. Requirements buried in usage guidelines rather than highlighted where needed.

**How to avoid:**

- Prominently document required headers (e.g., User-Agent for Open Library)
- Show exact header format with placeholder examples
- Explain difference between identified vs anonymous requests
- Include authentication in quickstart (first thing after base URL)
- Clarify test vs production credentials if applicable

**Warning signs:**

- Authentication docs buried deep in "Usage Guidelines"
- No example showing headers in request
- User-Agent requirement mentioned but not demonstrated

**Phase to address:**
Quickstart & Authentication Documentation

---

### Pitfall 4: Incomplete Response Schema Documentation

**What goes wrong:**
Response fields documented incompletely. Developers don't know if fields can be null, what empty values mean, or which fields are always present vs optional.

**Why it happens:**
Only "interesting" fields documented. Null-handling, optional fields considered implementation details.

**How to avoid:**

- Document every field in response
- Specify data type for each field
- Note which fields can be null/missing
- Explain what null or empty values signify
- Link to source schema but explain in human-readable form

**Warning signs:**

- Response shown with ellipsis ("...") for brevity
- Fields referenced in examples but never explained
- Schema link provided as substitute for documentation
- "Additional fields may be included" without specifics

**Phase to address:**
Endpoint Documentation - Response schema for each endpoint

---

### Pitfall 5: Rate Limits Unclear or Hidden

**What goes wrong:**
Developers hit rate limits unexpectedly. No clarity on what happens when limits exceeded or how to check remaining quota.

**Why it happens:**
Rate limits seen as technical details. Documentation vague ("generous limits") rather than specific.

**How to avoid:**

- State exact limits (requests per second/minute)
- Document which headers show remaining quota
- Explain behavior when limited (response code, retry-after)
- Distinguish between identified and anonymous limits
- Provide guidance on batching to avoid limits

**Warning signs:**

- Rate limits described as "reasonable" or "generous" without numbers
- No mention of 429 responses
- No headers documented for quota tracking

**Phase to address:**
Usage Guidelines / Rate Limiting Section

---

### Pitfall 6: No Troubleshooting Section

**What goes wrong:**
Developers stuck on common issues with no help. Same questions asked repeatedly in support channels.

**Why it happens:**
Common problems considered "obvious" to those who wrote the docs. No feedback loop from developers struggling.

**How to avoid:**

- Create dedicated troubleshooting section
- Cover: connection failures, authentication errors, rate limiting, empty responses
- Include "why is my request returning nothing?" type questions
- Add debugging tips (how to verify request/response)
- Link to community forums or support channels

**Warning signs:**

- No troubleshooting or FAQ section
- Support channels not linked from docs
- Common errors not explained

**Phase to address:**
Troubleshooting Section Creation

---

### Pitfall 7: Inconsistent Documentation Patterns

**What goes wrong:**
Different endpoints documented differently. One uses `x-api-key`, another uses `Authorization: Bearer`. Response formats vary unpredictably.

**Why it happens:**
Documentation written at different times by different people. No style guide enforced.

**How to avoid:**

- Create documentation template/standard for all endpoints
- Use consistent format: endpoint, method, parameters, request example, response example, errors
- Review all endpoints for consistency before publishing
- Document naming conventions (camelCase vs snake_case)

**Warning signs:**

- Authentication method varies across endpoints
- Response field naming inconsistent
- Different error formats per endpoint

**Phase to address:**
Documentation Planning - Establish standards before writing

---

## Technical Debt Patterns

| Shortcut                               | Immediate Benefit        | Long-term Cost                       | When Acceptable                     |
| -------------------------------------- | ------------------------ | ------------------------------------ | ----------------------------------- |
| Link to source code for schema         | Saves documentation time | Developers hate navigating to GitHub | Never for public docs               |
| Use curl examples only                 | Simple to write          | Excludes non-command-line users      | Only as supplement, not replacement |
| Document only "happy path"             | Faster initial docs      | Developers can't handle errors       | Never                               |
| Skip error codes for obscure endpoints | Saves time               | Breaks developer trust universally   | Never                               |
| Write docs once, never update          | No maintenance           | Examples become wrong, trust lost    | Never                               |

## Integration Gotchas

| Integration       | Common Mistake                            | Correct Approach                                 |
| ----------------- | ----------------------------------------- | ------------------------------------------------ |
| User-Agent header | Not including it or using wrong format    | Document exact format: `AppName (contact@email)` |
| Rate limits       | Assuming unlimited or not checking limits | Document limits, provide way to check quota      |
| Response caching  | Not caching when API encourages it        | Document caching recommendations                 |
| Batch requests    | Making hundreds of single requests        | Document batch endpoints (e.g., search.json)     |

## Performance Traps

| Trap                     | Symptoms                           | Prevention                               | When It Breaks      |
| ------------------------ | ---------------------------------- | ---------------------------------------- | ------------------- |
| No pagination guidance   | Loading all results                | Document offset/limit or page parameters | Large result sets   |
| N+1 request pattern      | Making separate call for each item | Document batch/bulk endpoints            | Any non-trivial use |
| Not using JSON endpoints | Scraping HTML                      | Document JSON API priority over HTML     | Always              |

## Security Mistakes

| Mistake                         | Risk                     | Prevention                                  |
| ------------------------------- | ------------------------ | ------------------------------------------- |
| Not identifying application     | Rate limiting/blocking   | Document User-Agent requirement prominently |
| Distributing traffic across IPs | Aggressive rate limiting | Document that this violates guidelines      |
| Using API for bulk scraping     | Account termination      | Link to bulk data dumps instead             |

## UX Pitfalls

| Pitfall                               | User Impact                          | Better Approach                               |
| ------------------------------------- | ------------------------------------ | --------------------------------------------- |
| Quickstart requires reading 5 pages   | Developers give up before first call | Get-to-working-example in under 2 minutes     |
| No search in docs                     | Can't find what they need            | Add functional search                         |
| Navigation doesn't match mental model | Can't find endpoint docs             | Organize by user task, not internal structure |
| No mobile-friendly docs               | Can't read on phone                  | Responsive design required                    |

## "Looks Done But Isn't" Checklist

- [ ] **Code examples:** Actually copy-paste and run them — verify they work
- [ ] **Authentication:** Can a developer get authenticated in under 5 minutes?
- [ ] **Error handling:** Can developers handle every error without guessing?
- [ ] **Rate limits:** Are exact numbers documented, not vague terms?
- [ ] **Response schema:** Is every field explained with type and nullability?
- [ ] **Quickstart:** Does it result in a successful API call?
- [ ] **Troubleshooting:** Can developers debug common issues without support?
- [ ] **Multi-language:** Are examples provided in major languages (JS, Python)?

## Recovery Strategies

| Pitfall               | Recovery Cost | Recovery Steps                                             |
| --------------------- | ------------- | ---------------------------------------------------------- |
| Broken examples       | MEDIUM        | Test all examples, fix syntax, update response samples     |
| Missing error docs    | HIGH          | Audit all endpoints for error responses, add documentation |
| Auth confusion        | LOW           | Add prominent auth section, show header examples           |
| Inconsistent patterns | MEDIUM        | Create template, update all endpoints to match             |

## Pitfall-to-Phase Mapping

| Pitfall                     | Prevention Phase             | Verification                                   |
| --------------------------- | ---------------------------- | ---------------------------------------------- |
| Non-Working Code Examples   | Documentation Implementation | Run all examples as part of CI                 |
| Missing Error Documentation | Documentation Implementation | Review each endpoint for error coverage        |
| Authentication Confusion    | Quickstart Development       | Developer test: can they auth in 5 min?        |
| Incomplete Response Schema  | Endpoint Documentation       | Audit each response for field coverage         |
| Rate Limits Unclear         | Usage Guidelines             | Verify all limits have numbers, not adjectives |
| No Troubleshooting          | Documentation Implementation | Check support tickets for undocumented issues  |
| Inconsistent Patterns       | Documentation Planning       | Apply style guide review before publishing     |

## Sources

- [API Documentation: Good, Bad, and Unusable](https://dev.to/apiverve/api-documentation-good-bad-and-unusable-47jh) - DEV Community
- [Common API Documentation Errors](https://robertdelwood.medium.com/common-api-documentation-errors-45ba3a25c212) - Robert Delwood
- [8 Unmissable API Documentation Best Practices for 2025](https://kdpisda.in/8-unmissable-api-documentation-best-practices-for-2025/)
- [API documentation best practices guide Feb 2026](https://buildwithfern.com/post/api-documentation-best-practices-guide) - Fern
- Open Library Developer Center (https://openlibrary.org/developers/api) - Current docs reviewed

---

_Pitfalls research for: Open Library API Documentation_
_Researched: 2026-03-04_
