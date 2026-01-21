# Guide: Migrating web.py Endpoints to FastAPI

## Overview
Quick reference for migrating OpenLibrary endpoints from web.py to FastAPI based on the `subjects_json` migration experience.

## Key Principles

### 1. Start with Manual Integration Tests
**Always create a test script first** that compares actual HTTP responses between web.py (port 8080) and FastAPI (port 18080):
```bash
#!/bin/bash
# Test real HTTP responses
webpy_response=$(curl -s "http://localhost:8080/endpoint.json?param=value")
fastapi_response=$(curl -s "http://localhost:18080/endpoint.json?param=value")

# Compare structure (keys, types, values)
```

This is more important than pytest unit tests and catches actual behavioral differences.

### 2. Follow Existing FastAPI Patterns

Look at `openlibrary/fastapi/search.py` for the template:
- Use Pydantic models for request validation
- Use `Annotated[Model, Depends()]` for query parameters
- Return dict[str, Any] or use response models

### 3. URL Path Handling

**Web.py with `encoding='json'`**:
- Path: `'(/subjects/[^/]+)'`
- Actual URL: `/subjects/love.json` (includes `.json`)
- The path regex doesn't include `.json` but web.py adds it when `encoding='json'`

**FastAPI**:
- Path: `/subjects/{key:path}.json`
- Must include `.json` explicitly in the route
- Use `{key:path}` to capture colons in values (e.g., `person:mark_twain`)

### 4. Validation Strategy

**For simple validation** (limit checks, etc.):
```python
# In the endpoint function (NOT in Pydantic validators)
if params.limit > MAX_RESULTS:
    raise HTTPException(
        status_code=400,
        detail={"error": f"Specified limit exceeds maximum of {MAX_RESULTS}."},
    )
```

Avoid Pydantic `field_validator` for business logic - use it only for type validation. Use HTTPException in the endpoint body for proper 400 responses.

### 5. Don't Reconstruct What Already Exists

**❌ Wrong (overcomplicated):**
```python
subject = get_subject(...)
results = {
    "key": subject.key,
    "name": subject.name,
    # ... manually add every field
}
if details:
    if hasattr(subject, "subjects"):
        results["subjects"] = ...
    # ... manually handle each facet
```

**✅ Right (simple):**
```python
subject = get_subject(...)
results = dict(subject)  # Subject is web.storage (dict-like)
results["works"] = [dict(w) for w in subject.works]  # Convert nested objects
```

The underlying functions already populate everything. Just serialize what they return.

### 6. Import Location for Mocking

When mocking in tests:
- Web.py imports from: `openlibrary.plugins.worksearch.subjects`
- FastAPI imports from: `openlibrary.plugins.worksearch.subjects` (same)
- But you need to mock at the **import location in each module**:
  - Mock web.py: `patch('openlibrary.plugins.worksearch.subjects.get_subject')`
  - Mock FastAPI: `patch('openlibrary.fastapi.subjects.get_subject')`

### 7. Use `web.storage` for Mocks

In test fixtures, use `web.storage()` for mock objects (it's dict-like):
```python
@pytest.fixture
def mock_get_subject():
    with patch('openlibrary.plugins.worksearch.subjects.get_subject') as mock:
        mock.return_value = web.storage(
            key='/subjects/love',
            name='Love',
            # ... minimal fields
        )
        yield mock
```

### 8. Run Pre-commit Early

Run `pre-commit run --all-files` before declaring done. It will:
- Auto-fix formatting with black/ruff
- Catch import issues
- Validate configuration

## Common Pitfalls

❌ **Don't**: Reconstruct response fields that the underlying function already provides
❌ **Don't**: Use complex Pydantic validators for business logic
❌ **Don't**: Forget that `encoding='json'` means `.json` is in the URL
❌ **Don't**: Spend too much time on pytest if manual tests already pass

✅ **Do**: Start with manual integration tests (cURL comparisons)
✅ **Do**: Use `dict(subject)` to serialize web.storage objects
✅ **Do**: Match web.py's simple approach - just pass through what functions return
✅ **Do**: Handle special cases (like ebook_count) minimally

## Files to Modify for New Endpoint

1. Create `openlibrary/fastapi/{feature}.py` - The FastAPI endpoint
2. Modify `openlibrary/asgi_app.py` - Register the router: `app.include_router(router)`
3. Create `test_{feature}_migration.sh` - Manual integration tests
4. Optionally: Add tests to `openlibrary/tests/fastapi/test_api_contract.py`

## Success Criteria

- Manual integration tests show identical responses
- Pre-commit hooks pass
- Code is simpler than web.py version (not more complex)
- Follows existing patterns in `openlibrary/fastapi/search.py`
