"""Guards against drift between the two copies of the availability taxonomy.

`AVAILABILITY_TO_PARAMS` is defined twice — once in Python
(`openlibrary/plugins/worksearch/code.py`, used to render filtered URLs and
detect the active availability server-side) and once in JavaScript
(`openlibrary/plugins/openlibrary/js/search-modal/constants.js`, used by the
header search modal and the /search filter row to build the same URLs
client-side without a round-trip). The two genuinely run in different runtimes,
so a single shared literal isn't practical; this test makes any divergence fail
CI instead of relying on the "keep in sync" comment.

Both files are parsed from source (no imports) so the test stays cheap and free
of the infogami/web runtime the worksearch code otherwise needs.
"""

import ast
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[4]
PY_SOURCE = REPO_ROOT / "openlibrary" / "plugins" / "worksearch" / "code.py"
JS_SOURCE = REPO_ROOT / "openlibrary" / "plugins" / "openlibrary" / "js" / "search-modal" / "constants.js"


def _python_availability_to_params() -> dict[str, dict[str, str]]:
    """Extract the AVAILABILITY_TO_PARAMS literal from code.py via the AST, so we
    read the real value without importing the module (which pulls infogami)."""
    tree = ast.parse(PY_SOURCE.read_text())
    for node in ast.walk(tree):
        # The Python copy carries a type annotation, so it's an AnnAssign
        # (`NAME: type = {...}`) rather than a plain Assign — handle both.
        targets: list[ast.expr]
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            continue
        if node.value is not None and any(isinstance(t, ast.Name) and t.id == "AVAILABILITY_TO_PARAMS" for t in targets):
            return ast.literal_eval(node.value)
    raise AssertionError("AVAILABILITY_TO_PARAMS not found in code.py")


def _extract_js_literal(source: str, name: str) -> str:
    """Return the bracket-balanced literal (`{...}` object or `[...]` array)
    assigned to `export const <name>`."""
    start = source.index(f"export const {name}")
    opens = {"{": "}", "[": "]"}
    open_idx = min(
        (source.index(ch, start) for ch in opens if ch in source[start:]),
        default=-1,
    )
    if open_idx < 0:
        raise AssertionError(f"No literal found for {name} in constants.js")
    open_ch = source[open_idx]
    close_ch = opens[open_ch]
    depth = 0
    for i in range(open_idx, len(source)):
        if source[i] == open_ch:
            depth += 1
        elif source[i] == close_ch:
            depth -= 1
            if depth == 0:
                return source[open_idx : i + 1]
    raise AssertionError(f"Unbalanced brackets extracting {name} from constants.js")


def _js_literal_to_python(literal: str):
    """Convert a small JS object/array literal (the availability config) to a
    Python value: strip line comments, quote bare keys, swap quote style, drop
    trailing commas, then json.loads. Deliberately narrow — it only needs to
    handle the stable, comment-annotated availability literals."""
    no_comments = re.sub(r"//[^\n]*", "", literal)
    quoted_keys = re.sub(r"([{,]\s*)([A-Za-z_]\w*)(\s*):", r'\1"\2"\3:', no_comments)
    double_quoted = quoted_keys.replace("'", '"')
    no_trailing = re.sub(r",(\s*[}\]])", r"\1", double_quoted)
    return json.loads(no_trailing)


def _js_availability_to_params() -> dict[str, dict[str, str]]:
    source = JS_SOURCE.read_text()
    return _js_literal_to_python(_extract_js_literal(source, "AVAILABILITY_TO_PARAMS"))


def _js_availability_option_values() -> list[str]:
    source = JS_SOURCE.read_text()
    array = _js_literal_to_python(_extract_js_literal(source, "AVAILABILITY_OPTIONS"))
    return [opt["value"] for opt in array]


def test_availability_to_params_python_matches_js():
    """The param mappings must be identical across the two runtimes."""
    assert _python_availability_to_params() == _js_availability_to_params()


def test_availability_value_set_is_consistent():
    """The availability values the UI offers (AVAILABILITY_OPTIONS) must be
    exactly the keys the param mapping knows how to materialize, on both sides —
    no orphaned option that maps to nothing, no param key with no UI value."""
    py_params = _python_availability_to_params()
    js_params = _js_availability_to_params()
    option_values = _js_availability_option_values()

    assert set(option_values) == set(py_params)
    assert set(option_values) == set(js_params)
