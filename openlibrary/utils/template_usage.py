"""Static analysis to find templates and macros that are never referenced.

Open Library renders pages with two template systems side by side:

* Templetor (web.py/Infogami) -- ``openlibrary/templates/**/*.html`` page
  templates (referenced as ``"account/mybooks"``) and
  ``openlibrary/macros/*.html`` macros (referenced by bare file stem, e.g.
  ``CoverImage``).
* Jinja -- ``*.html.jinja`` files in both roots, referenced by their full path
  relative to the Jinja loader roots (``openlibrary/macros`` then
  ``openlibrary/templates``), e.g. ``"design/layout.html.jinja"``.

This module inventories every template/macro file plus every Jinja
``{% macro %}`` definition, then searches every git-tracked source file
(Python, Templetor, Jinja, JS/TS/Vue, config) for references.  Anything with
no reference is reported as unused.

The analysis is deliberately conservative: it prefers to miss an unused
template over flagging one that is actually used, because a false positive
fails the build and invites deleting a template that is still live.
References that cannot be seen statically are handled in two ways:

* ``DYNAMIC_DISPATCH_RULES`` documents directories whose templates are
  resolved at runtime by name construction (DB type keys, changeset kinds,
  provider registries, design-system section ids) -- those are always
  considered used, and so are the Jinja macros defined inside them (they are
  imported under dynamic aliases such as ``page.nav()``).
* Templates/macros that are used only from *database* content (wiki-stored
  templates under ``/upstream/templates/*``, wiki-stored macros, or
  ``{{Macro(...)}}`` markdown in any page body) are invisible to static
  analysis.  The pytest wrapper keeps an explicit exclusion list for those;
  see ``openlibrary/tests/test_unused_templates.py``.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOTS = (
    REPO_ROOT / "openlibrary" / "templates",
    REPO_ROOT / "openlibrary" / "macros",
)

KIND_TEMPLETOR_TEMPLATE = "templetor template"
KIND_TEMPLETOR_MACRO = "templetor macro"
KIND_JINJA_TEMPLATE = "jinja template"
KIND_JINJA_MACRO = "jinja macro"

# File types that may contain template references (Python code, both template
# systems' files, front-end sources, and config).  Docs (*.md) are excluded:
# a template mentioned in documentation is not used by it.  Test files are
# included on purpose -- a template rendered only from a test is still alive.
CORPUS_SUFFIXES = frozenset({".py", ".js", ".ts", ".tsx", ".vue", ".html", ".jinja", ".yml", ".yaml", ".json"})

# Files never scanned for references.  This module and its test mention
# template names verbatim (exclusion lists, rule tables), and package-lock.json
# is generated noise whose dependency names could rescue a template by
# coincidence.
CORPUS_SKIP_FILES = frozenset(
    {
        "openlibrary/utils/template_usage.py",
        "openlibrary/tests/test_unused_templates.py",
        "package-lock.json",
    }
)

# Directories under openlibrary/templates/ whose files are never referenced by
# a literal name: the runtime builds their names dynamically.  Mapped to the
# code that does the dispatch, so the rule can be checked and updated.
DYNAMIC_DISPATCH_RULES: dict[str, str] = {
    "type/": (
        "selected by infogami's typetemplate() as "
        "render[<db type key> + '/' + name] -- the type keys live in the "
        "database, not the code (infogami/utils/template.py)"
    ),
    "recentchanges/": (
        "selected from DB changeset kinds via get_template('recentchanges/' + "
        "kind + '/...') with recentchanges/default/... fallback "
        "(openlibrary/plugins/upstream/recentchanges.py, "
        "openlibrary/plugins/upstream/utils.py, "
        "templates/recentchanges/render.html)"
    ),
    "book_providers/": ("filename constructed as f'book_providers/{short_name}_{typ}.html' from the provider registry (openlibrary/book_providers.py)"),
    "design/": (
        "imported dynamically by Jinja as 'design/' + section.id + "
        "'.html.jinja' and via the component registry component.partial "
        "(templates/design/layout.html.jinja, "
        "openlibrary/plugins/openlibrary/design.py)"
    ),
}

JINJA_MACRO_DEF_RE = re.compile(r"{%-?\s*macro\s+(\w+)\s*\(")


@dataclass(frozen=True)
class Template:
    """A template/macros file, or a single {% macro %} definition in one."""

    name: str
    path: Path
    kind: str

    @property
    def relpath(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()

    @property
    def rel_to_root(self) -> str:
        """Path relative to its template root (macros/ or templates/)."""
        for root in TEMPLATE_ROOTS:
            if self.path.is_relative_to(root):
                return self.path.relative_to(root).as_posix()
        return self.relpath


@dataclass
class Analysis:
    """Result of the unused-template scan."""

    templates: list[Template]
    unused: list[Template]
    # Exclusion-list entries that are actually referenced in code (so the
    # entry hides real usage and must be removed), mapped to the evidence.
    used_exclusions: dict[str, str]
    # Exclusion-list entries with no matching template/macro on disk.
    missing_exclusions: set[str]


def iter_template_files() -> list[Template]:
    templates = []
    for root in TEMPLATE_ROOTS:
        is_macros_root = root.name == "macros"
        for path in sorted(root.rglob("*.html")):
            # Templetor resolves names with any extension stripped, so the
            # canonical name is the path relative to the root minus ".html".
            name = path.relative_to(root).as_posix()[: -len(".html")]
            kind = KIND_TEMPLETOR_MACRO if is_macros_root else KIND_TEMPLETOR_TEMPLATE
            templates.append(Template(name, path, kind))
        for path in sorted(root.rglob("*.html.jinja")):
            # Jinja resolves the full path relative to its loader roots.
            name = path.relative_to(root).as_posix()
            templates.append(Template(name, path, KIND_JINJA_TEMPLATE))
    return templates


def build_inventory() -> list[Template]:
    templates = iter_template_files()
    for t in templates:
        if t.kind != KIND_JINJA_TEMPLATE:
            continue
        text = t.path.read_text(encoding="utf-8", errors="replace")
        for match in JINJA_MACRO_DEF_RE.finditer(text):
            templates.append(Template(match.group(1), t.path, KIND_JINJA_MACRO))
    return sorted(set(templates), key=lambda t: (t.kind, t.relpath, t.name))


def build_corpus() -> dict[str, str]:
    """Read every git-tracked source file that may contain references.

    Only tracked files are scanned, so the result is hermetic: untracked
    scratch files, local config overrides, and nested checkouts cannot make
    the verdict differ between machines or CI.  ``--recurse-submodules`` is
    load-bearing -- references like ``render.viewpage`` live in the
    ``vendor/infogami`` submodule (initialize it with ``make git``).
    """
    files = (
        subprocess.run(
            ["git", "ls-files", "--recurse-submodules", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    if not any(rel.startswith("vendor/infogami/") for rel in files):
        raise RuntimeError(
            "git ls-files returned no vendor/infogami files -- the submodule "
            "is not initialized. Run `make git` (git submodule update --init) "
            "so the scan can see infogami's template references."
        )
    corpus: dict[str, str] = {}
    for rel in files:
        path = REPO_ROOT / rel
        if not path.is_file() or Path(rel).suffix not in CORPUS_SUFFIXES or rel in CORPUS_SKIP_FILES:
            continue
        corpus[rel] = path.read_text(encoding="utf-8", errors="replace")
    return corpus


QUOTED_LITERAL_RE = re.compile(r'"([^"\n]+)"|\'([^\'\n]+)\'')
WORD_RE = re.compile(r"\w+")
CALLED_WORD_RE = re.compile(r"\w+(?=\s*\()")
RENDER_ATTR_RE = re.compile(r"\brender\.(\w+)")


@dataclass(frozen=True)
class FileIndex:
    """Pre-extracted references from one corpus file.

    Scanning every file with a regex per template name is O(names x files x
    file size); extracting these sets once per file turns each usage check
    into O(1) set lookups.
    """

    # String literals (pair-matched quotes, nested other-type quotes one
    # level deep), each also stored with its last extension stripped:
    # render_template()/get_template() strip extensions at resolve time, so
    # "site/head.tmpl" and "lists/feed_updates.xml" both reference .html files.
    quoted: frozenset[str]
    # All word tokens.  Templetor macros are referenced by bare name wherever
    # they appear: $:macros.Name(...), render_macro("Name"),
    # CacheableMacro("Name") indirection, JS component names.  Names are
    # usually CamelCase but not always (i18n, iframe).
    words: frozenset[str]
    # Attributes accessed on `render` (render.notfound(...), render.site(...)).
    render_attrs: frozenset[str]
    # Words followed by "(" -- how Jinja macros are called (alias.name(...)).
    # Only extracted for .jinja files, the only place non-exempt macros live.
    called_words: frozenset[str]
    # Words on lines containing `import` ({% from "..." import a, b %}).
    import_words: frozenset[str]


@dataclass(frozen=True)
class SearchIndex:
    """Per-file indexes sorted by path, so evidence reporting is stable."""

    entries: tuple[tuple[str, FileIndex], ...]


def _add_quoted(text: str, quoted: set[str]) -> None:
    """Add every quoted literal in text (raw + extension-stripped).

    Recurses once into literals that themselves contain the other quote
    type, e.g. data-i18n="$:render_template('search/availability_i18n')"
    where the template name sits in single quotes inside an HTML attribute.
    """
    for match in QUOTED_LITERAL_RE.finditer(text):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        quoted.add(literal)
        if "." in literal:
            quoted.add(literal.rsplit(".", 1)[0])
        if "'" in literal or '"' in literal:
            _add_quoted(literal, quoted)


def _index_file(text: str, suffix: str) -> FileIndex:
    quoted: set[str] = set()
    _add_quoted(text, quoted)
    called_words: frozenset[str] = frozenset()
    import_words: frozenset[str] = frozenset()
    if suffix == ".jinja":
        # Jinja macro calls/imports only matter in .jinja files, so the
        # costlier extractions below run there and nowhere else.
        called_words = frozenset(CALLED_WORD_RE.findall(text))
        import_words = frozenset(word for line in text.splitlines() if re.search(r"\bimport\b", line) for word in WORD_RE.findall(line))
    return FileIndex(
        quoted=frozenset(quoted),
        words=frozenset(WORD_RE.findall(text)),
        render_attrs=frozenset(RENDER_ATTR_RE.findall(text)),
        called_words=called_words,
        import_words=import_words,
    )


def build_search_index(corpus: dict[str, str]) -> SearchIndex:
    return SearchIndex(entries=tuple((rel, _index_file(text, Path(rel).suffix)) for rel, text in sorted(corpus.items())))


def _macro_used_in_own_file(text: str, name: str) -> bool:
    """Whether a Jinja macro is called inside its own defining file.

    Self-use counts as usage (helper macros composing other macros in the
    same file), but the ``{% macro name(`` definition lines do not.
    """
    for match in re.finditer(rf"\b{re.escape(name)}\s*\(", text):
        if re.search(r"macro\s*$", text[: match.start()]):
            continue
        return True
    return False


def dynamic_dispatch_note(template: Template) -> str | None:
    """Dispatch note if this template is only reachable via name construction.

    Directories in ``DYNAMIC_DISPATCH_RULES`` never appear literally in call
    sites: the runtime builds their names from DB type keys, changeset kinds,
    provider registries, or design-system section ids.
    """
    rel_to_root = template.rel_to_root
    if template.kind == KIND_JINJA_MACRO:
        if rel_to_root.startswith(tuple(DYNAMIC_DISPATCH_RULES)):
            # Macros inside dynamically-imported files are called through
            # dynamic aliases (e.g. page.nav()), which no pattern can see.
            return "defined in a dynamically imported template"
        return None
    for prefix, why in DYNAMIC_DISPATCH_RULES.items():
        if rel_to_root.startswith(prefix):
            return f"dynamically dispatched ({why})"
    return None


def _reference_sets(template: Template, file_index: FileIndex) -> tuple[frozenset[str], ...]:
    """The token sets of ``file_index`` a reference to ``template`` lives in."""
    if template.kind == KIND_TEMPLETOR_TEMPLATE:
        # Named in string literals (render_template("account/login")); a
        # root-level template is also reachable as render.name(...) attribute
        # access on infogami's Render DictPile.
        if "/" not in template.name:
            return file_index.quoted, file_index.render_attrs
        return (file_index.quoted,)
    if template.kind == KIND_TEMPLETOR_MACRO:
        return (file_index.words,)
    if template.kind == KIND_JINJA_TEMPLATE:
        return (file_index.quoted,)
    # Jinja macros are called as name(...) or named by {%- import %} lines;
    # aliased imports are covered because the name is its own word in
    # alias.name(...).
    return file_index.called_words, file_index.import_words


def find_usage(template: Template, index: SearchIndex) -> str | None:
    """Return evidence (a corpus path or dispatch note) that this is used."""
    if note := dynamic_dispatch_note(template):
        return note

    self_rel = template.relpath
    for rel, file_index in index.entries:
        # A file's own contents never count as a reference from elsewhere;
        # self-referencing Jinja macros are handled separately below.
        if rel == self_rel:
            continue
        if any(template.name in tokens for tokens in _reference_sets(template, file_index)):
            return rel
    if template.kind == KIND_JINJA_MACRO and _macro_used_in_own_file(
        template.path.read_text(encoding="utf-8", errors="replace"),
        template.name,
    ):
        return f"{self_rel} (self-referencing macro)"
    return None


def analyze(exclusions: Iterable[str] = ()) -> Analysis:
    """Scan the code base and report unused templates/macros.

    ``exclusions`` are names to skip (used only from database content); they
    are also audited so stale entries -- ones actually referenced in code, or
    matching nothing on disk -- surface as errors.
    """
    corpus = build_corpus()
    inventory = build_inventory()
    index = build_search_index(corpus)

    unused = [t for t in inventory if t.name not in exclusions and find_usage(t, index) is None]

    used_exclusions: dict[str, str] = {}
    missing_exclusions: set[str] = set()
    for name in exclusions:
        matches = [t for t in inventory if t.name == name]
        if not matches:
            missing_exclusions.add(name)
            continue
        for t in matches:
            if evidence := find_usage(t, index):
                used_exclusions[name] = evidence

    return Analysis(
        templates=inventory,
        unused=unused,
        used_exclusions=used_exclusions,
        missing_exclusions=missing_exclusions,
    )
