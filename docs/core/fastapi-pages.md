# Serving HTML pages from FastAPI

How to move a web.py page to FastAPI. The page is a Jinja template wrapped in the shared site shell (header, footer, head) from `openlibrary/core/shell/`, which renders the same on both servers. The reference port is `/advancedsearch`: the route, its query model and its nav dependency are at the end of `openlibrary/fastapi/search.py`, and its tests are in `openlibrary/tests/fastapi/test_advancedsearch.py`. Copy those.

For Jinja syntax and Templetor→Jinja conversion, see [`docs/wiki/developers/frontend/jinja.md`](/developers/frontend/jinja.md).

## The rule: only the route touches the request

`web.ctx` and infogami's `context` are thread-locals that FastAPI never resets. A sync route's worker thread keeps whatever the last request on it left, and async routes share the event loop thread's. Read either from a FastAPI request and one user's path, flash message or cookie can end up in another user's page.

So only the route (and `SitePageRoute`, for the shell) sees the request. The route declares typed inputs, FastAPI builds them, and everything below gets plain values: no `Request`, no `web.ctx`, no `web.input()`, and no Templetor request globals (`ctx`, `query_param`, `changequery`) in the template.

## The shape of a page route

```python
pages = APIRouter(route_class=SitePageRoute)  # once per router module, next to its JSON `router`


@pages.get("/advancedsearch")
async def advancedsearch(form: Annotated[AdvancedSearchForm, Query()], nav: SearchNavDep) -> SitePage:
    body = render_jinja_template("search/advancedsearch.html.jinja", form=form, nav=nav)
    return SitePage(body, page=PageMeta(title=_("Advanced Search")))
```

A route returns its body as a `SitePage`, and `SitePageRoute` (`openlibrary/fastapi/shared/site_page.py`) wraps it in the shell, as infogami's `layout_processor` does on web.py. The route never sees the shell's inputs. For every route on the router, `SitePageRoute` also:

- rejects forged `vf` and session cookies with a 403 before the route runs, as web.py's `CookieValidationProcessor` does for every page. nginx only challenges suspicious requests that carry no cookies, so without this a bot skips the challenge by sending any cookie;
- loads the logged-in user for the shell after the route runs, only if it returned a `SitePage`: a redirect or an error costs no lookup. If the route took `CurrentUserDep`, the shell reuses that user;
- builds the shell's request values (`ShellRequest`) from the request;
- expires the flash cookie once its messages are shown;
- adds the headers and cookies set on FastAPI's injected `Response` (a `response: Response` argument, in the route or a dependency) to whatever the route returns. FastAPI itself drops them when a route returns a response, as page routes do. A header the returned response sets wins, but all cookies are sent and `Vary` values are merged. A status code set on the injected `Response` is ignored, as in FastAPI; pass it to `SitePage`;
- answers HEAD as well as GET, as web.py does;
- leaves the route out of the OpenAPI schema.

Other responses (a redirect, an error) pass through unchanged. A route that can return either a page or a redirect is annotated `-> Response`. A `SitePage` returned from a route on a plain `APIRouter` raises instead of being served without the shell. Include the `pages` router in the HTML pages block at the end of `_include_routers` in `openlibrary/asgi_app.py`.

There is no page-body helper: the route passes its typed inputs straight to `render_jinja_template`, per the jinja guide's "do not make a thin Python wrapper".

Each argument has one job:

| Argument | What it is | Who reads it |
|---|---|---|
| `form` | Pydantic model of the page's query params | the page template |
| `nav` | A small frozen dataclass built from the request by a dependency | a shared partial (the search tabs) |

## Steps

1. **Convert the template to Jinja.** Put a comment at the top naming the values it takes (`{# Takes `form` (AdvancedSearchForm) and `nav` (SearchNav) #}`). Shared partials take one object, like `SearchNavigation.html.jinja` takes `nav`. A Templetor page that still includes the partial passes a dict with the same keys.

2. **Declare query params as a Pydantic model**: `Annotated[Model, Query()]`. Defaults, normalisation and fallbacks (like `subject_facet` filling `subject`) go in the model's validators. Don't hand-parse `request.query_params`. Unknown params are ignored, and a repeated scalar param keeps its last value, as `web.input()` does (declare `list[str]` for params that repeat on purpose, like `author_key`). If the page has a JSON twin (`/search` and `/search.json`), share the fields and their normalisation with the JSON endpoint through a base model, but keep that base lenient, and let the JSON model narrow it in a subclass.
   - The JSON models reject requests the HTML page has to render: `/search.json?q=x` and `/search.json?q=tolkien&has_fulltext=yes` are 422s, but web.py's `/search` renders both.
   - Lenient means plain `str` fields and no rejecting validators in the base. The strictness lives in types as well as validators: `PublicQueryOptions` (`fastapi/search.py`) has a `q` validator (at least 3 characters, not just "the") and `Literal["true", "false"]` fields, so it can't be the base as it is. The JSON subclass narrows the types (`int`, `Literal`) and adds the validators.
   - Decide what the page does with input it can't use (`page=abc`): fall back to a default and render, or render an error page. web.py's `/search?page=abc` is a 500 today; don't copy that.

3. **Put any other request-derived value in a dependency.** Write a frozen dataclass with a `from_request(request)` classmethod and expose it as an `XxxDep = Annotated[Xxx, Depends(Xxx.from_request)]` alias (see `SearchNav`). Use this for anything a template needs beyond the query fields, such as the current path or a link carrying the query string. Shared ones go in `openlibrary/fastapi/shared/dependencies.py`.

4. **Return `SitePage(body, page=PageMeta(...))`.** `PageMeta` carries what Templetor pages set with `$var`/`$putctx`: title, CSS file, body classes and attributes, links, meta tags. Always pass a title; without one it's the URL path, as on web.py. The shell escapes the title, `bodyattrs`, `links` and `metatags`, so a book title or a URL can go in as it is. Wrap HTML you built yourself (a `<link>`, a `<meta>`) in `markupsafe.Markup`, and build it with `Markup(...).format(...)`, which escapes what goes into it. web.py's values come through as `Markup`, because Templetor escaped them already.

5. **Take `CurrentUserDep` if the page needs the user.** It's the logged-in user (a `ShellUser`: key, join date, librarian flags), or `None` for a visitor, looked up once per request and shared with the shell. Don't call `get_current_user()` from `openlibrary.accounts`, which makes a second lookup and blocks the event loop in an `async` route. `fastapi/auth.py`'s `require_authenticated_user` and `LibrarianDep` are a separate check for now; merging them with `CurrentUserDep` is planned (RAY-89).

6. **Use `async def` unless the body blocks.** The user lookup isn't the route's concern: `SitePageRoute` and `CurrentUserDep` run it in a worker thread, and the shell itself does no I/O. So a route whose body is pure (like `/advancedsearch`) or awaits async calls is `async def`. A route that calls blocking code (`site.get()`, sync `db`, `requests`) is `def`, so FastAPI runs it in a worker thread; the ContextVars that `asgi_app.py`'s middleware sets (`site`, `req_context`) are copied into it.

   The user lookup is sync for now (see the TODO on `load_shell_user` in `openlibrary/core/shell/user.py`). Once it reads infobase through `openlibrary/core/infobase_async.py`, it's awaited and page requests need no worker thread at all.

7. **Port everything a path serves, together.** Production sends a path to FastAPI or web.py by path alone, and FastAPI has no fallback to web.py there (dev and testing do). So before a path moves, FastAPI must serve everything web.py serves on it. Compare against web.py directly (`http://web:8080` in dev) before you route it:
   - **Every method.** A page with a form needs its POST too.
   - **Every format, chosen by `Accept` header or suffix.** infogami picks the response format on the same path (`find_encoding` in `vendor/infogami/infogami/utils/app.py`): `Accept: application/json` on `/works/OL1W` returns JSON, not HTML, and so do `.json`, `.rdf`, `.yml`, `.opds` and `.marcxml` suffixes (registered in `openlibrary/plugins/openlibrary/code.py`). API clients depend on these. A FastAPI route that only renders HTML would break every one of them.
   - **Every infogami view, chosen by `?m=`.** These are `delegate.mode` classes: `edit`, `history`, `diff`, `permission`, `backlinks`, `review`, `approve`, `revert`, `change_cover`, and the `rdf`, `opds`, `marcxml` and `yml` formats (`vendor/infogami/infogami/core/code.py`, `vendor/infogami/infogami/plugins/`, `openlibrary/plugins/upstream/code.py`, `openlibrary/plugins/openlibrary/code.py`). Old revisions are `?v=N`. These also combine with `Accept`: `?m=history` with `Accept: application/json` returns JSON.
   - **Every URL shape.** Work, edition and author pages redirect to a slug URL (`/works/OL1W` → `/works/OL1W/Title`), so the route must take `{id}/{slug}` too, and keep the redirects. The same applies to a trailing slash (`/advancedsearch/` redirects today).

8. **Keep the web.py handler as a thin wrapper, then delete it.** Production still sends a path to web.py until the proxy config (in the ops repo) routes it to FastAPI. Until then, the web.py handler builds the same inputs and renders the same template, with the same title:

   ```python
   def GET(self):
       # Local imports: openlibrary.fastapi.search imports this module, and this handler is temporary.
       from markupsafe import escape

       from openlibrary.core.jinja import render_jinja_template
       from openlibrary.fastapi.search import AdvancedSearchForm, SearchNav

       params = web.input(_method="get")
       form = AdvancedSearchForm.model_validate(dict(params))
       body = render_jinja_template("search/advancedsearch.html.jinja", form=form, nav=SearchNav.from_query(web.ctx.path, params))
       # web.py's layout reads the title off the result, already escaped, as from Templetor's $var.
       return web.template.TemplateResult(__body__=body, title=escape(_("Advanced Search")))
   ```

   A dependency that web.py also needs gets a second constructor taking plain values (`SearchNav.from_query(path, params)`), which `from_request` calls. Once production routes the path to FastAPI, delete the handler and the Templetor template. Check what else web.py answered under that handler first: it serves `/advancedsearch.json` (the HTML page) and redirects `/advancedsearch/`. Those 404 once it's gone, unless the haproxy entry matches the path as a prefix or the FastAPI route answers them.

## Tests to copy

`openlibrary/tests/fastapi/test_advancedsearch.py` has the three that matter for every port. The fixtures they use are in `openlibrary/tests/fastapi/conftest.py`:

- `site_page_app(*routers)` builds an app with your page router, logged in as the `x-user` header's user and with no infobase.
- `webpy_leftovers` fills `web.ctx` and infogami's `context` with another request's state, every value containing `LEFTOVER`.
- `fetch_concurrently(app, requests)` sends requests at once, so they interleave.

The three tests:

- **Isolation.** Run interleaved requests with `webpy_leftovers` set, and check each page shows only its own query and never `LEFTOVER`. This proves the page body reads nothing from the thread-locals. The shell's own isolation (user, flash messages, language) is tested once, in `openlibrary/tests/fastapi/test_site_page.py`.
- **Parity.** While the web.py handler exists, the web.py and FastAPI bodies for the same query are identical.
- **Inputs.** Escaping, fallbacks, repeated and unknown params.

## Where code goes

| What | Where |
|---|---|
| Route, query model, page dependencies | The domain's `pages` router in `openlibrary/fastapi/` (search pages: `fastapi/search.py`) |
| Dependencies shared across routers | `openlibrary/fastapi/shared/dependencies.py` |
| `SitePage`, `SitePageRoute`, `CurrentUserDep` | `openlibrary/fastapi/shared/site_page.py` |
| Site shell (`ShellRequest`, `PageMeta`, `ShellUser`, layout builders) | `openlibrary/core/shell/` |
| Templates | `openlibrary/templates/` and `openlibrary/macros/`, as `*.html.jinja` |
