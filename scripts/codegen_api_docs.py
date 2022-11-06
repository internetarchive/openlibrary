#!/usr/bin/env python3

import inspect
import sys
from types import CodeType, ModuleType
from collections.abc import Iterator


def enhance_query_arg(arg: str, default_type: str = "Optional[str]") -> str:
    """
    Add Python type hints to function arguments where possible.

    >>> [enhance_query_arg(arg) for arg in (" x ", " x = -1234 ", "x=-5", "x=-67.89")]
    ['x', 'x: int = -1234', 'x: int = -5', 'x: float = -67.89']
    >>> [enhance_query_arg(arg) for arg in ("x=[ ]", "x=None", 'x=""','x="text"')]
    ['x: list = [ ]', 'x: Optional[str] = None', 'x: str = ""', 'x: str = "text"']
    >>> [enhance_query_arg(arg) for arg in ("x=true", "x=FALSE", '  x  =  tRUE  ')]
    ['x: bool = True', 'x: bool = False', 'x: bool = True']
    """
    key, _, value = (item.strip() for item in arg.partition("="))
    if not value:
        return key
    type_hint = {
        "[]": "Optional[list]",
        "''": "str",
        '""': "str",
        "None": default_type,
        "True": "bool",
        "False": "bool",
    }.get(value.title(), "")
    if type_hint:
        value = "None" if value == "[]" else value.title()
    elif value.lstrip("-").isdigit():
        type_hint = "int"
    elif value.lstrip("-").replace(".", "", 1).isdigit():
        type_hint = "float"
    elif any(value.startswith(q) and value.endswith(q) for q in ("'", '"')):
        type_hint = "str"
    elif value.startswith("[") and value.endswith("]"):
        type_hint = "list"
    return f"{key}: {type_hint or default_type} = {value}"


def get_query_args(code: CodeType, method_call: str = "web.input(") -> list[str]:
    """
    Look thru the lines of code looking for `method_call` and if found, extract
    the parameters and enhance them with Python type hints and default values.

    NOTE: Failure case if a method parameter is a tuple!
    """
    code_str = "".join(line.strip() for line in inspect.getsource(code))
    _, _, code_str = code_str.partition(method_call)  # Only the text after method_call
    if not code_str:
        return []
    return [enhance_query_arg(arg) for arg in code_str.split(")")[0].split(",")]


def insert_args_into_url_path(
    url_path: str, path_args: tuple[str, ...]
) -> tuple[str, dict[str, str]]:
    """
    >>> insert_args_into_url_path("/authors/(OL\\d+A)/edit", ("key", ))
    ('/authors/{key}/edit', {'key': 'OL\\\\d+A'})
    >>> insert_args_into_url_path("/these/are/the/parts", ())
    ('/these/are/the/parts', {})
    >>> insert_args_into_url_path("/works/(OL\\d+W)/observations", ("work_id", ))
    ('/works/{work_id}/observations', {'work_id': 'OL\\\\d+W'})
    >>> url_path = r"/data/ol_cdump_(\\d\\d\\d\\d-\\d\\d-\\d\\d).txt.gz"
    >>> insert_args_into_url_path(url_path, ("date", ))
    ('/data/ol_cdump_{date}.txt.gz', {'date': '\\\\d\\\\d\\\\d\\\\d-\\\\d\\\\d-\\\\d\\\\d'})
    >>> url_path = ("/data/ol_dump(|_authors|_editions|_works|_deworks|_ratings"
    ...             "|_reading-log)_(\\\\d\\\\d\\\\d\\d-\\\\d\\\\d-\\\\d\\\\d).txt.gz")
    >>> path_args = ("prefix", "date")
    >>> insert_args_into_url_path(url_path, path_args) # doctest: +NORMALIZE_WHITESPACE
    ('/data/ol_dump{prefix}_{date}.txt.gz',
     {'prefix': '|_authors|_editions|_works|_deworks|_ratings|_reading-log',
      'date': '\\\\d\\\\d\\\\d\\\\d-\\\\d\\\\d-\\\\d\\\\d'})
    """
    regexes = {}
    for arg in path_args:
        start = url_path.index("(")
        finish = url_path.index(")")
        assert start < finish
        regexes[arg] = url_path[start + 1 : finish]
        url_path = f"{url_path[:start]}{{{arg}}}{url_path[finish + 1 :]}"
    return url_path, regexes


def get_url_path(
    url_path: str, path_args: tuple[str, ...]
) -> tuple[str, dict[str, str]]:
    """
    >>> get_url_path("(/authors/OL\\d+A)/edit", path_args = ("key", ))
    ('/authors/{key}/edit', {'key': 'OL\\\\d+A'})
    >>> get_url_path(url_path = "/these/are/the/parts", path_args = ())
    ('/these/are/the/parts', {})
    """
    assert url_path.count("(") == url_path.count(")"), f"{url_path = }, {path_args = }"
    if url_path != "/admin(?:/.*)?":  # TODO: How does this url_path work?
        assert len(path_args) == url_path.count("("), f"{url_path = }, {path_args = }"
    if not path_args:
        return url_path, {}

    if url_path.startswith("("):  # Move a leading parenthesis to first part with ")"
        parts = url_path.strip("(/").split("/")
        for i, part in enumerate(parts):
            if ")" in part:
                parts[i] = f"({part}"
                url_path = "/" + "/".join(parts)
                break

    if "/OL(" in url_path:  # Convert "OL(\d+)A" --> "(OL\d+A)" for Pydantic validation
        parts = url_path.strip("/").split("/")
        for i, part in enumerate(parts):
            if part.startswith("OL("):
                parts[i] = f"({part.replace('(', '').replace(')', '')})"
        url_path = "/" + "/".join(parts)

    return insert_args_into_url_path(url_path, path_args)


get_fmt = '''@app.get("{url_path}")
async def {classname}_get({method_params}) -> str:
    """
    {docstring}
    """
    {body_code}
'''


def webpy_to_fastapi(api_details: dict) -> str:
    """
    Codegen a FastAPI async function from the web.py GET function api_details.
    """
    code: CodeType = api_details["get_code"]
    assert code.co_varnames[0] == "self", code.co_varnames
    start = int(code.co_varnames[0] == "self")  # 1 to skip "self" else 0
    path_args = code.co_varnames[start : code.co_argcount]  # noqa: E203
    query_args = get_query_args(code)

    url_path, regexes = get_url_path(api_details["url_path"], path_args)
    url = f"https://openlibrary.org{url_path}"
    url_params = ", params=locals()" if query_args else ""
    d = {
        "method_params": ", ".join(list(path_args) + query_args),
        "body_code": f'return requests.get("{url}"{url_params}).json()',
    }
    for key in ("url_path", "classname", "docstring"):
        d[key] = api_details[key]
    if regexes:  # TODO: Convert regexes into Pytdantic validations
        d["docstring"] += f"\n\n    {regexes = }"
    return get_fmt.format(**d)


def get_api_details(module: ModuleType = sys.modules[__name__]) -> Iterator[dict]:
    """
    Codegen FastAPI async functions from the web.py GET functions in this file.
    If a class has a `path` attribute and a `GET()` or `get()` method then yield info.
    """
    for classname, cls in inspect.getmembers(module, inspect.isclass):
        if classname in ('account_login'):  # Drop any undesirable classes
            continue
        if not getattr(cls, "path", None):  # @app.get path: '/works/OL(\d+)W/editions'
            continue
        get = getattr(cls, "GET", getattr(cls, "get", None))  # Find the GET() method
        if get and get.__qualname__.startswith(classname):  # Ignore inherited funcs
            wrapped = getattr(get, "__wrapped__", False)  # See Python @functools.wraps
            code = get.__wrapped__.__code__ if wrapped else get.__code__
            yield {
                "url_path": cls.path,
                "classname": classname,
                "get_code": code,
                "docstring": (
                    inspect.cleandoc(get.__doc__ or "")
                    or f"{cls.__module__}.{classname}_get{inspect.signature(get)}"
                ),
            }


IMPORTS = """
#!/usr/bin/env python3

from enum import Enum
from typing import Any, Optional

import requests
from fastapi import FastAPI

DEFAULT_RESULTS = "DEFAULT_RESULTS"
RESULTS_PER_PAGE = 20

app = FastAPI()
url_base = "https://openlibrary.org"
"""


if __name__ == "__main__":
    from doctest import testmod
    from itertools import chain
    from operator import itemgetter
    from time import perf_counter

    import _init_path  # noqa: F401
    from openlibrary.plugins.openlibrary import api

    """
    import (
        author_works,
        public_observations,
        ratings,
        trending_books_api,
        work_bookshelves,
        work_editions,
    )
    """
    from openlibrary.plugins.openlibrary import lists  # lists_json
    from openlibrary.plugins.worksearch import code as worksearch  # search_json

    """
    from openlibrary.plugins.admin import code as admin
    from openlibrary.plugins.books import code as books
    from openlibrary.plugins.inside import code as search_inside
    from openlibrary.plugins.openlibrary import (
        api,
        authors,
        borrow_home,
        design,
        home,
        status,
        support,
    )
    from openlibrary.plugins.upstream import (
        account,
        addbook,
        borrow,
        covers,
        data,
        merge_authors,
        mybooks,
        code as upstream,
    )
    from openlibrary.plugins.worksearch import (
        languages,
        publishers,
        subjects,
        code as worksearch,
    )

    testmod()  # Run our doctests before running codegen.

    start = perf_counter()
    modules = (
        account,
        addbook,
        admin,
        api,
        authors,
        books,
        borrow,
        borrow_home,
        covers,
        data,
        design,
        home,
        languages,
        merge_authors,
        mybooks,
        publishers,
        search_inside,
        status,
        subjects,
        support,
        upstream,
        worksearch,
    )
    """
    testmod()  # Run our doctests before running codegen.

    start = perf_counter()
    modules = api, lists, worksearch
    print(IMPORTS)
    func_iter = chain.from_iterable(get_api_details(module) for module in modules)
    functions = sorted(func_iter, key=itemgetter("url_path"))
    elapsed_time = perf_counter() - start
    print("\n\n".join(webpy_to_fastapi(function) for function in functions))
    print(
        f"# Finished generating {len(functions)} functions in {elapsed_time:0.6} seconds."
    )
