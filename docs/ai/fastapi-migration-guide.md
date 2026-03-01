# FastAPI Migration Guide

This guide explains how to migrate web.py JSON endpoints to FastAPI in Open Library.

## Overview

Open Library is gradually migrating from web.py (Infogami) to FastAPI. This guide shows how to convert JSON endpoints that use `@jsonapi` decorator or `encoding = "json"`.

## Important Notes

- **Do NOT write unit tests** - They are not useful for this type of migration
- **Test by comparing endpoints** - Create a comparison script that checks old vs new endpoints
- **Use `uv run` for scripts** - Specify dependencies with modern uv format
- **Handle `.json` extensions** - Many web.py endpoints require paths ending in `.json`
- **Set up web context** - Legacy code uses `web.ctx.get("home")` which needs proper setup in FastAPI

## Current State

- **Legacy:** web.py endpoints in `openlibrary/plugins/` using `delegate.page` classes
- **Modern:** FastAPI endpoints in `openlibrary/fastapi/` using FastAPI routers
- **Run:** `uv run scripts/find_json_delegate_pages.py .` to find all JSON endpoints

## Migration Pattern

### 1. Understand the web.py Endpoint

Example web.py endpoint (`openlibrary/plugins/books/code.py`):

```python
class books_json(delegate.page):
    path = "/api/books"

    @jsonapi
    def GET(self):
        i = web.input(bibkeys='', callback=None, details="false", high_priority=False)
        i.high_priority = i.get("high_priority") == "true"
        if web.ctx.path.endswith('.json'):
            i.format = 'json'
        return dynlinks.dynlinks(bib_keys=i.bibkeys.split(","), options=i)
```

Key elements:
- Inherits from `delegate.page`
- Has `path` attribute (regex pattern)
- Uses `@jsonapi` decorator or `encoding = "json"`
- Uses `web.input()` for query parameters
- Returns data that's auto-converted to JSON

### 2. Create FastAPI Endpoint

Example FastAPI equivalent (`openlibrary/fastapi/books.py`):

```python
import json
from typing import Annotated, Literal

import web
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, BeforeValidator, Field

from openlibrary.plugins.books import dynlinks

router = APIRouter()


def parse_bibkeys(v: str | list[str]) -> list[str]:
    """Parse comma-separated bibliography keys into a list."""
    if isinstance(v, str):
        v = [v]
    return [f.strip() for item in v for f in str(item).split(",") if f.strip()]


class BooksAPIQueryParams(BaseModel):
    """Query parameters for Books API endpoint."""

    bibkeys: Annotated[list[str], BeforeValidator(parse_bibkeys)] = Field(
        ..., description="Comma-separated list of bibliography keys"
    )
    callback: str | None = Field(None, description="JSONP callback function name")
    details: Literal["true", "false"] = Field("false", description="Include detailed information")
    jscmd: Literal["details", "data", "viewapi"] | None = Field(None, description="Format of returned data")
    high_priority: bool = Field(False, description="Attempt import immediately")


@router.get("/api/books.json")
async def get_books(
    request: Request,
    params: Annotated[BooksAPIQueryParams, Query()],
) -> dict:
    """
    Get book metadata by bibliography keys.

    Supports ISBN, LCCN, OCLC, etc.

    Example:
        GET /api/books.json?bibkeys=059035342X,0312368615&high_priority=true
    """
    # Set up web context for legacy code compatibility
    web.ctx.home = f"{request.url.scheme}://{request.url.netloc}"

    # Build options dict from Pydantic model
    options = {
        'format': 'json',
    }

    if params.callback:
        options['callback'] = params.callback
    if params.details:
        options['details'] = params.details
    if params.jscmd:
        options['jscmd'] = params.jscmd
    if params.high_priority:
        options['high_priority'] = params.high_priority

    # Reuse existing business logic (bibkeys already parsed by validator)
    result_str = dynlinks.dynlinks(bib_keys=params.bibkeys, options=options)

    # Parse JSON result (import json at module level!)
    return json.loads(result_str)
```

And mark the old web.py endpoint as deprecated:

```python
# openlibrary/plugins/books/code.py
from typing_extensions import deprecated

@deprecated("migrated to fastapi")
class books_json(delegate.page):
    path = "/api/books"
```

### 3. Register Router in ASGI App

Add to `openlibrary/asgi_app.py`:

```python
from openlibrary.fastapi.books import router as books_router

app.include_router(books_router)
```

## Key Differences

| web.py | FastAPI |
|--------|---------|
| `class Foo(delegate.page)` | `router = APIRouter()` |
| `path = "/api/..."` | `@router.get("/api/...")` |
| `def GET(self):` | `async def endpoint(...):` |
| `web.input(param="default")` | `param: type = Query(default, ...)` |
| `web.ctx.path` | `request.url.path` (Request dependency) |
| `return data` | `return data` (auto-serialized via Pydantic) |
| `@jsonapi` decorator | `response_model=...` |

## Converting Patterns

**Important Rule:** For web.py endpoints with `encoding = "json"`, ONLY register `.json` path in FastAPI. Do not register non-JSON versions.

### Path Parameters

```python
@router.get("/api/endpoint.json")
async def get_endpoint(request: Request, ...):
    # Endpoint logic here
```

**Important:** For web.py endpoints with `encoding = "json"`, ONLY register the `.json` version. Non-JSON paths are not needed.

### Setting Up `web.ctx` Context

Legacy code often uses `web.ctx.get("home")` or `web.ctx.path`. Set these up in FastAPI:

```python
import web
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/api/endpoint.json")
async def get_endpoint(request: Request, ...):
    # Set up web context for legacy compatibility
    web.ctx.home = f"{request.url.scheme}://{request.url.netloc}"

    # Your endpoint logic here
```

This ensures URLs and context variables work correctly with legacy business logic.

## Converting Patterns

### Path Parameters

**web.py:**
```python
path = r"/api/volumes/(brief|full)/(isbn|lccn)/(.+)"
def GET(self, brief_or_full, idtype, idval):
    req = f'{idtype}:{idval}'
    # ...
```

**FastAPI:**
```python
@router.get("/api/volumes/{brief_or_full}/{idtype}/{idval}")
async def get_volume(
    brief_or_full: Literal["brief", "full"],
    idtype: Literal["isbn", "lccn", "oclc", "olid"],
    idval: str,
):
    req = f'{idtype}:{idval}'
    # ...
```

### Query Parameters

**web.py:**
```python
def GET(self):
    i = web.input(q="", limit=10, offset=0)
    query = i.q
    limit = int(i.limit)
```

**FastAPI:**
```python
@router.get("/search")
async def search(
    q: str = Query("", description="Search query"),
    limit: int = Query(10, description="Number of results", ge=1, le=100),
    offset: int = Query(0, description="Offset for pagination", ge=0),
):
    # No conversion needed, types are enforced
```

### POST with Body

**web.py:**
```python
def POST(self):
    data = json.loads(web.data())
    name = data.get('name')
```

**FastAPI:**
```python
class CreateRequest(BaseModel):
    name: str = Field(..., description="Name")
    description: str | None = Field(None, description="Description")

@router.post("/create")
async def create(request: CreateRequest):
    # request is already parsed and validated
    name = request.name
```

### JSON Response

**web.py:**
```python
return {"key": "value", "nested": {"data": 123}}
```

**FastAPI:**
```python
class Response(BaseModel):
    key: str
    nested: dict

@router.get("/endpoint")
async def endpoint() -> Response:
    return Response(key="value", nested={"data": 123})
```

## Authentication

For endpoints that require authentication:

**web.py:**
```python
from infogami.utils.view import public

class MyEndpoint(delegate.page):
    @public
    def GET(self):
        user = delegate.context.user
        if not user:
            raise web.unauthorized()
```

**FastAPI:**
```python
from openlibrary.fastapi.auth import (
    AuthenticatedUser,
    require_authenticated_user,
)
from typing import Annotated

# Optional auth (returns None if not authenticated)
@router.get("/endpoint")
async def endpoint(
    user: Annotated[AuthenticatedUser | None, Depends(get_authenticated_user)],
):
    if user:
        return {"username": user.username}
    else:
        return {"message": "Not authenticated"}

# Required auth (returns 401 if not authenticated)
@router.post("/protected")
async def protected(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
):
    return {"username": user.username}
```

## Testing

### Do NOT Write Unit Tests

Unit tests are not useful for this type of migration because:
- They don't verify real-world behavior
- They don't catch compatibility issues with legacy endpoints
- Business logic is already tested elsewhere

### Use Pydantic Models for Query Parameters

Instead of defining all query parameters individually, use Pydantic models to group related parameters:

**❌ Bad (individual parameters):**
```python
@router.get("/api/endpoint")
async def get_endpoint(
    bibkeys: str = Query(..., description="Bibliography keys"),
    details: Literal["true", "false"] = Query("false"),
    high_priority: bool = Query(False),
):
    # Manually build options dict
    options = {
        'bibkeys': bibkeys.split(","),
        'details': details,
        'high_priority': high_priority,
    }
```

**✅ Good (Pydantic model):**
```python
from typing import Annotated

class EndpointQueryParams(BaseModel):
    """Query parameters for endpoint."""
    bibkeys: str = Field(..., description="Bibliography keys")
    details: Literal["true", "false"] = Field("false")
    high_priority: bool = Field(False)

@router.get("/api/endpoint.json")
async def get_endpoint(
    params: Annotated[EndpointQueryParams, Depends()],
):
    # Use params directly, no manual dict building needed
    options = {
        'bibkeys': params.bibkeys.split(","),
        'details': params.details,
        'high_priority': params.high_priority,
    }
```

Benefits of using Pydantic models:
- Groups related parameters together
- Automatic validation and type checking
- Reusable across endpoints
- Better documentation in OpenAPI schema
- Cleaner endpoint function signatures

### Use Field Validators for Data Transformation

Instead of manually parsing strings in endpoint body, use Pydantic validators to transform data:

**❌ Bad (manual parsing in endpoint):**
```python
@router.get("/api/books.json")
async def get_books(
    bibkeys: str = Query(..., description="Bibliography keys"),
):
    # Manual string splitting in endpoint body
    bib_keys_list = [key.strip() for key in bibkeys.split(",") if key.strip()]
    result = some_function(bib_keys=bib_keys_list)
```

**✅ Good (BeforeValidator with Annotated):**
```python
from typing import Annotated
from pydantic import BaseModel, BeforeValidator, Field

def parse_bibkeys(v: str | list[str]) -> list[str]:
    """Parse comma-separated bibliography keys into a list."""
    if isinstance(v, str):
        v = [v]
    return [f.strip() for item in v for f in str(item).split(",") if f.strip()]

class BooksAPIQueryParams(BaseModel):
    bibkeys: Annotated[list[str], BeforeValidator(parse_bibkeys)] = Field(
        ..., description="Bibliography keys"
    )

@router.get("/api/books.json")
async def get_books(
    request: Request,
    params: Annotated[BooksAPIQueryParams, Query()],
) -> dict:
    # bibkeys is already parsed as list[str]
    result = some_function(bib_keys=params.bibkeys)
```

Benefits of using `BeforeValidator`:
- Less business logic in endpoint body
- Data transformation happens automatically
- Reusable validation logic
- Cleaner endpoint functions
- Type-safe transformations

### Mark Legacy Endpoints as Deprecated

After migrating an endpoint, add `@deprecated` decorator to the old web.py class:

```python
from typing_extensions import deprecated

@deprecated("migrated to fastapi")
class books_json(delegate.page):
    path = "/api/books"
```

This helps developers know the endpoint has been migrated.

### DO Import Dependencies at Module Level

Never import modules inside endpoint functions. All imports should be at the top of the file:

**❌ Bad:**
```python
@router.get("/api/endpoint")
async def get_endpoint(...):
    import json  # Don't do this!
    return json.loads(data)
```

**✅ Good:**
```python
import json  # Import at top level

@router.get("/api/endpoint")
async def get_endpoint(...):
    return json.loads(data)
```

### DO Test Endpoints Manually with curl

After implementing an endpoint, manually test it with curl to verify it works:

```bash
curl "http://localhost:18080/api/books.json?bibkeys=0452010586"
```

This helps catch:
- Import errors
- Runtime errors
- Missing dependencies
- Type validation issues
- Response format problems

Test with various parameters to ensure all code paths work.

**Tip:** If you get validation errors like "Field required", check that your parameter model uses `Query()` not `Depends()`, and that validators properly transform string inputs to the expected types.

### DO Mark Integration Tests with @pytest.mark.integration

Integration tests in `tests/integration/temporary/` must be:

1. **Marked with `@pytest.mark.integration` decorator** - To skip during normal runs
2. **Proper pytest test functions** - Must start with `test_` prefix
3. **No main() function** - Tests should use pytest assertions, not return codes

```python
import pytest
import requests

@pytest.mark.integration
def test_books_api_single():
    """Test books API with single ISBN."""
    old_response = requests.get("http://localhost:8080/api/books.json", params={"bibkeys": "059035342X"})
    new_response = requests.get("http://localhost:18080/api/books.json", params={"bibkeys": "059035342X"})

    assert old_response.status_code == 200
    assert new_response.status_code == 200
    assert old_response.json() == new_response.json()
```

This ensures tests are:
- Skipped during normal pytest runs (`make pytest`)
- Only run when explicitly requested with `make test-py` or `-m integration`
- Discovered properly by pytest (functions starting with `test_`)

**Why?** Integration tests require external services (web.py on port 8080, FastAPI on port 18080) and should not run in normal CI/CD pipelines that test business logic.

### DO Write Comparison Scripts

Create a comparison script that tests both old and new endpoints:

```python
#!/usr/bin/env python3
"""Test script to verify API migration returns same results."""

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "requests",
# ]
# ///

import json
import sys

import requests

OLD_BASE = "http://localhost:8080"
NEW_BASE = "http://localhost:18080"


def test_endpoint(endpoint, params):
    """Test both old and new endpoints and compare results."""
    old_url = f"{OLD_BASE}{endpoint}"
    new_url = f"{NEW_BASE}{endpoint}"

    old_response = requests.get(old_url, params=params)
    new_response = requests.get(new_url, params=params)

    old_data = old_response.json()
    new_data = new_response.json()

    if old_data == new_data:
        print("✅ Results match!")
        return True
    else:
        print(f"❌ Results differ: {old_data} vs {new_data}")
        return False


if __name__ == "__main__":
    test_cases = [
        ("/api/books.json", {"bibkeys": "059035342X"}),
        ("/api/books.json", {"bibkeys": "059035342X,0312368615"}),
    ]

    passed = sum(test_endpoint(ep, params) for ep, params in test_cases)
    print(f"Results: {passed}/{len(test_cases)} passed")
    sys.exit(0 if passed == len(test_cases) else 1)
```

Run with: `uv run scripts/test_books_migration.py`

**Note:** Make sure both servers are running (`docker compose up`) before testing.

### Integration Tests

Compare old and new endpoints:

```python
def test_migration_compatibility():
    old_response = requests.get("http://localhost:8080/api/books?bibkeys=059035342X")
    new_response = requests.get("http://localhost:18080/api/books?bibkeys=059035342X")

    assert old_response.json() == new_response.json()
```

## Best Practices

1. **Reuse Business Logic**: Don't rewrite business logic. Import from existing modules (e.g., `dynlinks`, `readlinks`).

2. **Pydantic Models**: Define clear request/response models. This provides:
   - Automatic validation
   - OpenAPI documentation
   - Type safety

3. **Maintain Backward Compatibility**:
   - Keep same URL paths
   - Keep same parameter names
   - Keep same response structure
   - Handle edge cases the same way

4. **Error Handling**:
   ```python
   from fastapi import HTTPException

   @router.get("/endpoint")
   async def endpoint(id: str):
       try:
           result = get_data(id)
       except ValueError as e:
           raise HTTPException(status_code=400, detail=str(e))
       return result
   ```

5. **Documentation**:
   - Add docstrings to endpoints
   - Add Field descriptions to Pydantic models
   - Use `description` parameter for Query/Path

6. **Keep it Simple**:
   - Don't make endpoints async unless you need to
   - Business logic can remain synchronous
   - FastAPI handles both sync and async

## Migration Checklist

- [ ] Create FastAPI router file in `openlibrary/fastapi/`
- [ ] Define Pydantic models for request/response
- [ ] Implement endpoint(s) with same path and parameters
- [ ] Reuse existing business logic from web.py file
- [ ] Add unit tests for new endpoints
- [ ] Test backward compatibility with old endpoints
- [ ] Register router in `openlibrary/asgi_app.py`
- [ ] Update documentation if needed
- [ ] Verify OpenAPI docs work (http://localhost:18080/docs)

## Example: Full Migration

See `openlibrary/fastapi/partials.py` for a complete example of migrated endpoints. The old `openlibrary/plugins/openlibrary/partials.py` is marked as `[DEPRECATED: migrated to fastapi]`.

## Best Practices Summary

1. ✅ **ONLY register `.json` paths for `encoding = "json"` endpoints**
2. ✅ **Use Pydantic models for query parameters** - Don't define individual parameters unless there are very few
3. ✅ **Import dependencies at module level** - Never import inside endpoint functions
4. ✅ **Set up `web.ctx` context** - Required for legacy business logic. Only when needed.
5. ✅ **Reuse existing business logic** - Don't rewrite, import and call
6. ✅ **Test with comparison scripts** - Verify old vs new endpoints match
7. ✅ **Include in OpenAPI schema** - Never use `include_in_schema=False` for migrations

## Migration Checklist
