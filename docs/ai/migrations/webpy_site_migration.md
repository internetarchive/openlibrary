# Migration Plan: web.ctx.site to FastAPI ContextVar

## Problem

The codebase currently uses `web.ctx.site` (~586 references) to access the Infogami Site object for database operations. This won't work in FastAPI because `web.ctx` is thread-local and doesn't work properly in async contexts.

## Goal

Replace all `web.ctx.site` usage with a ContextVar-based approach that works in both web.py (during transition) and FastAPI.

## Design Decision: SiteProxy Pattern

Instead of calling `site.get()` everywhere or using a helper function, we'll use a **SiteProxy** class that delegates attribute access to the underlying ContextVar:

```python
# In openlibrary/utils/request_context.py:

class SiteProxy:
    """
    Proxy to the site ContextVar.

    This allows code to use `site.get(key)` instead of having to
    call `site.get().get(key)` or a helper function.

    When accessed, it looks up the ContextVar in the CURRENT async
    context - this is safe because FastAPI middleware sets it BEFORE
    the handler runs.
    """

    def __getattr__(self, name: str):
        """Delegate all attribute access to the actual site."""
        return getattr(site.get(), name)


# The raw ContextVar (kept for internal use in request_context.py)
site_contextvar: ContextVar[Site] = ContextVar("site")

# Export the proxy as `site` for public use
site = SiteProxy()
```

### Why SiteProxy?

| Approach                | Syntax  | Issues                                    |
| ----------------------- | ------- | ----------------------------------------- |
| `web.ctx.site.get(key)` | Clean   | ❌ Doesn't work in FastAPI (thread-local) |
| `site.get().get(key)`   | Ugly    | ❌ Verbose, easy to forget `.get()`       |
| `get_site().get(key)`   | Verbose | ❌ Helper function everywhere             |
| `site.get(key)` (proxy) | Clean   | ✅ Works in both frameworks               |

The proxy gives us the same clean syntax as `web.ctx.site` while working in async contexts.

### Error Handling

The proxy will let `LookupError` propagate if called outside a request context. This is intentional - it indicates a programming bug that should fail fast rather than silently returning wrong data.

## Implementation Steps

### Step 1: Implement SiteProxy in request_context.py

Add the basic `SiteProxy` class:

```python
from contextvars import ContextVar

# The ContextVar (internal use - renamed to avoid conflict with proxy)
site_contextvar: ContextVar[Site] = ContextVar("site")


class SiteProxy:
    """
    Proxy to the site ContextVar.

    This allows code to use `site.get(key)` instead of having to
    call `site.get().get(key)` or a helper function.
    """

    def __getattr__(self, name: str):
        """Delegate all attribute access to the actual site."""
        return getattr(site_contextvar.get(), name)

    def set(self, value: Site):
        """Set the site in the ContextVar."""
        site_contextvar.set(value)

    def get(self) -> Site:
        """Get the site from the ContextVar."""
        return site_contextvar.get()


# Export the proxy as `site` for public use
site = SiteProxy()
```

Update `setup_site()` and `set_context_from_fastapi()` to use `site.set()`.

#### Step 1b: Add test suite for SiteProxy

Create `openlibrary/utils/tests/test_site_proxy.py`:

```python
"""Tests for SiteProxy."""

import pytest
from unittest.mock import Mock, MagicMock
from contextvars import ContextVar


class TestSiteProxy:
    """Test that SiteProxy correctly delegates to the ContextVar."""

    def test_getattr_delegates_to_site(self):
        """site.foo should delegate to the underlying site.foo."""
        from openlibrary.utils.request_context import site

        mock_site = Mock()
        mock_site.get = Mock(return_value="result")
        mock_site.some_method = Mock(return_value="method_result")

        site.set(mock_site)

        # Test method delegation
        assert site.get("key") == "result"
        assert site.some_method() == "method_result"

    def test_getattr_caches_per_context(self):
        """Each context should have its own site."""
        from openlibrary.utils.request_context import site

        mock_site1 = Mock()
        mock_site1.name = "site1"

        mock_site2 = Mock()
        mock_site2.name = "site2"

        # Set in main context
        site.set(mock_site1)
        assert site.name == "site1"

        # Create a new context and set a different site
        ctx = contextvars.copy_context()
        ctx.run(site.set, mock_site2)

        # Main context should still have site1
        assert site.name == "site1"

    def test_lookup_error_outside_context(self):
        """Should raise LookupError if called outside request context."""
        from openlibrary.utils.request_context import site

        # Reset the context
        site.set(None)  # or use ContextVar.reset()

        with pytest.raises(LookupError):
            site.get()  # This should fail

    def test_nested_context_isolation(self):
        """Nested contexts should have isolated site values."""
        from openlibrary.utils.request_context import site

        mock_site_outer = Mock()
        mock_site_outer.name = "outer"

        mock_site_inner = Mock()
        mock_site_inner.name = "inner"

        site.set(mock_site_outer)

        # Simulate inner context
        old = site.get()
        site.set(mock_site_inner)
        try:
            assert site.name == "inner"
        finally:
            site.set(old)

        # Outer context should be restored
        assert site.name == "outer"

    def test_property_access(self):
        """site.property should work."""
        from openlibrary.utils.request_context import site

        mock_site = Mock()
        mock_site.store = Mock()
        mock_site.store.get = Mock(return_value={"key": "value"})

        site.set(mock_site)

        # Access nested property
        result = site.store.get("some/key")
        assert result == {"key": "value"}
        mock_site.store.get.assert_called_once_with("some/key")

    def test_magic_methods_not_delegated(self):
        """Magic methods like __repr__ should not delegate to site."""
        from openlibrary.utils.request_context import site

        # These should work on the proxy itself
        repr_str = repr(site)
        assert "SiteProxy" in repr_str

        str_str = str(site)
        assert "SiteProxy" in str_str
```

Run tests with:

```bash
docker compose run --rm home pytest openlibrary/utils/tests/test_site_proxy.py -v
```

> **Note**: The basic SiteProxy doesn't include `conn` property or `as_user()` context manager yet. Those will be added later in Step 5 (after migrating the main codebase) to fix RunAs functionality.

### Step 2: Update existing files that already import from request_context

These files already import `site` from request_context and should work with minimal changes:

- `openlibrary/fastapi/public_my_books.py` - imports `site`
- `openlibrary/plugins/openlibrary/lists.py` - imports `site`
- `openlibrary/accounts/__init__.py` - imports `site`
- `openlibrary/core/fulltext.py` - imports `site`
- `openlibrary/mocks/mock_infobase.py` - imports `site as site_context`

**Action needed**: Verify these work after adding the proxy.

### Step 3: Migrate files using web.ctx.site (~30 files, ~586 references)

These files need to:

1. Import `site` from `openlibrary.utils.request_context`
2. Replace `web.ctx.site` with `site`

**Files to update** (sorted by reference count):

| File                                                       | Refs | Notes                  |
| ---------------------------------------------------------- | ---- | ---------------------- |
| `openlibrary/plugins/upstream/tests/test_addbook.py`       | 62   | Test file              |
| `openlibrary/accounts/model.py`                            | 42   |                        |
| `openlibrary/plugins/openlibrary/code.py`                  | 35   |                        |
| `openlibrary/plugins/admin/tests/test_code.py`             | 35   | Test file              |
| `openlibrary/plugins/openlibrary/lists.py`                 | 29   | Already imports `site` |
| `openlibrary/plugins/admin/code.py`                        | 23   |                        |
| `openlibrary/plugins/upstream/addbook.py`                  | 23   |                        |
| `openlibrary/core/models.py`                               | 22   |                        |
| `openlibrary/plugins/upstream/tests/test_merge_authors.py` | 21   | Test file              |
| `openlibrary/plugins/upstream/models.py`                   | 21   |                        |
| `openlibrary/plugins/upstream/utils.py`                    | 17   |                        |
| `openlibrary/plugins/upstream/borrow.py`                   | 16   |                        |
| `openlibrary/plugins/openlibrary/api.py`                   | 15   |                        |
| `openlibrary/catalog/add_book/__init__.py`                 | 13   |                        |
| `openlibrary/plugins/openlibrary/dev_instance.py`          | 11   |                        |
| `openlibrary/core/waitinglist.py`                          | 10   |                        |
| `openlibrary/plugins/upstream/tests/test_utils.py`         | 15   | Test file              |
| `openlibrary/plugins/upstream/recentchanges.py`            | 9    |                        |
| `openlibrary/plugins/upstream/spamcheck.py`                | 8    |                        |
| `openlibrary/plugins/upstream/covers.py`                   | 6    |                        |
| `openlibrary/plugins/upstream/mybooks.py`                  | 8    |                        |
| `openlibrary/plugins/upstream/merge_authors.py`            | 7    |                        |
| `openlibrary/plugins/openlibrary/home.py`                  | 6    |                        |
| `openlibrary/plugins/openlibrary/processors.py`            | 6    |                        |
| `openlibrary/plugins/books/dynlinks.py`                    | 4    |                        |
| `openlibrary/coverstore/code.py`                           | 4    |                        |
| `openlibrary/plugins/importapi/import_ui.py`               | 4    |                        |
| `openlibrary/core/lending.py`                              | 9    |                        |
| `openlibrary/core/processors/readableurls.py`              | 6    |                        |
| `openlibrary/core/processors/invalidation.py`              | 6    |                        |
| `openlibrary/plugins/worksearch/code.py`                   | 3    |                        |
| `openlibrary/plugins/worksearch/subjects.py`               | 2    |                        |
| `openlibrary/plugins/worksearch/publishers.py`             | 2    |                        |
| `openlibrary/plugins/worksearch/schemes/works.py`          | 1    |                        |
| `openlibrary/plugins/worksearch/autocomplete.py`           | 1    |                        |
| `openlibrary/plugins/upstream/tests/test_models.py`        | 6    | Test file              |
| `openlibrary/tests/core/test_processors_invalidation.py`   | 12   | Test file              |
| `openlibrary/plugins/importapi/tests/test_code.py`         | 4    | Test file              |
| `openlibrary/tests/core/test_helpers.py`                   | 2    | Test file              |
| `openlibrary/tests/core/test_i18n.py`                      | 1    | Test file              |

### Step 4: Update infogami's delegate.py (optional, for dual support)

The vendor/infogami code sets `web.ctx.site` in `delegate.py`. For dual-framework support during transition, we could also set the ContextVar there:

```python
# In vendor/infogami/infogami/utils/delegate.py
def create_site():
    # ... existing code ...
    s = client.Site(web.ctx.conn, site)

    # Also set the ContextVar for FastAPI compatibility
    from openlibrary.utils.request_context import set_site
    set_site(s)

    return s
```

**Note**: This would require adding a path from infogami back to openlibrary, which creates a circular dependency concern. May need to handle this differently.

### Step 5: Fix RunAs with context-aware site swapping

The `RunAs` class currently uses `web.ctx.conn.set_auth_token()` directly, which mutates shared connection state and doesn't work in FastAPI. We'll fix this by swapping the Site object in the ContextVar.

#### Step 5a: Add `as_user()` context manager to SiteProxy

```python
class SiteProxy:
    def __getattr__(self, name: str):
        return getattr(site_contextvar.get(), name)

    @contextmanager
    def as_user(self, username: str):
        """
        Temporarily run operations as a different user.

        Usage:
            with site.as_user('some_user'):
                # All site operations here run as some_user
                site.get(...)

        This creates a new Site with the desired auth token and swaps it
        in the ContextVar. On exit, the original Site is restored.
        """
        from openlibrary.accounts import find

        account = find(username=username)
        if not account:
            raise KeyError(f'Invalid username: {username}')

        # Save original site
        old_site = site_contextvar.get()

        # Create new site and set the auth token
        new_site = create_site()
        new_site._conn.set_auth_token(account.generate_login_code())

        site_contextvar.set(new_site)
        try:
            yield new_site
        finally:
            site_contextvar.set(old_site)
```

#### Step 5b: Update RunAs class

```python
# In openlibrary/accounts/__init__.py:
from openlibrary.utils.request_context import site

class RunAs:
    def __init__(self, username: str) -> None:
        self.username = username
        self.tmp_account = None

    def __enter__(self):
        from openlibrary.accounts import find
        self.tmp_account = find(username=self.username)
        if not self.tmp_account:
            raise KeyError('Invalid username')

        # Use site.as_user() context manager
        self._context = site.as_user(self.username)
        self._context.__enter__()
        return self.tmp_account

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._context.__exit__(exc_type, exc_val, exc_tb)
```

#### Step 5c: Update other RunAs usages

Also need to update these files that use `web.ctx.conn` directly:

- `openlibrary/plugins/upstream/account.py` - lines 442, 526
- `openlibrary/accounts/model.py` - line 963
- `openlibrary/accounts/__init__.py` - lines 46, 51

### Step 6: Test

Run the existing test suite to verify nothing broke:

```bash
make test-py
```

## Open Questions

1. **Should we keep dual support for web.py during transition?**

   - If yes, we need to update infogami's delegate.py
   - If no, we can just remove web.ctx.site usage entirely

2. **Should we create a compatibility shim for tests?**

   - Tests currently set `web.ctx.site = mock_site`
   - We may want to update them to set the ContextVar instead

3. **Should we use type hints?**
   - The proxy could benefit from `__getattr__` return type hints
   - Or we could use a Protocol/TypeAlias

## Related Files

- `openlibrary/utils/request_context.py` - Main implementation location
- `openlibrary/asgi_app.py` - Sets up context in FastAPI middleware
- `vendor/infogami/infogami/utils/delegate.py` - Creates site in web.py

## References

- Python ContextVars: https://docs.python.org/3/library/contextvars.html
- Related: `docs/ai/feature_flag_migration_plan.md` (similar migration pattern)
