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
``{% macro %}`` definition, then searches the code base (Python, Templetor,
Jinja, JS/TS/Vue, config files) for references.  Anything with no reference is
reported as unused.

The analysis is deliberately conservative: it prefers to miss an unused
template over flagging one that is actually used, because a false positive
fails the build and invites deleting a template that is still live.  References that cannot be seen statically are
handled in two ways:

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

import os
import re
import sys
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

# Directories never scanned for references (third-party code, build output, VCS).
CORPUS_SKIP_DIRS = frozenset(
    {
        "vendor",
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

# This module and its test must not count their own contents as references
# (the exclusion list and rule tables mention template names verbatim).
CORPUS_SKIP_FILES = frozenset(
    {
        "openlibrary/utils/template_usage.py",
        "openlibrary/tests/test_unused_templates.py",
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
    """Read every source file that may contain template references."""
    corpus: dict[str, str] = {}
    # followlinks: the top-level infogami/ directory is a symlink to
    # vendor/infogami/infogami, and references like render.viewpage live in
    # there.  vendor/ itself is pruned, so it is only read via the symlink.
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT, followlinks=True):
        dirnames[:] = sorted(d for d in dirnames if d not in CORPUS_SKIP_DIRS)
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix not in CORPUS_SUFFIXES:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in CORPUS_SKIP_FILES:
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
    # All word tokens, interned.  Templetor macros are referenced by bare
    # name wherever they appear: $:macros.Name(...), render_macro("Name"),
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
        words=frozenset(map(sys.intern, WORD_RE.findall(text))),
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
    rel_to_root = next(
        (template.path.relative_to(root).as_posix() for root in TEMPLATE_ROOTS if template.path.is_relative_to(root)),
        template.relpath,
    )
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


def find_usage(template: Template, index: SearchIndex) -> str | None:
    """Return evidence (a corpus path or dispatch note) that this is used."""
    if note := dynamic_dispatch_note(template):
        return note

    self_rel = template.relpath
    if template.kind == KIND_TEMPLETOR_TEMPLATE:
        # Root-level templates are also reachable as render.name(...)
        # attribute access on infogami's Render DictPile.
        check_render_attr = "/" not in template.name
        for rel, file_index in index.entries:
            if rel == self_rel:
                continue
            if template.name in file_index.quoted:
                return rel
            if check_render_attr and template.name in file_index.render_attrs:
                return rel
        return None
    elif template.kind == KIND_TEMPLETOR_MACRO:
        for rel, file_index in index.entries:
            if rel != self_rel and template.name in file_index.words:
                return rel
        return None
    elif template.kind == KIND_JINJA_TEMPLATE:
        for rel, file_index in index.entries:
            if rel != self_rel and template.name in file_index.quoted:
                return rel
        return None
    elif template.kind == KIND_JINJA_MACRO:
        # Calls always use parentheses; from-imports list names without
        # them.  Aliased imports are covered because the name is its own
        # word in alias.name(...).
        for rel, file_index in index.entries:
            if template.name in file_index.called_words or template.name in file_index.import_words:
                return rel
        if _macro_used_in_own_file(
            template.path.read_text(encoding="utf-8", errors="replace"),
            template.name,
        ):
            return f"{self_rel} (self-referencing macro)"
        return None
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
    # Cheap pre-filter: every usage pattern embeds the name literally, so a
    # name absent from the corpus text cannot possibly be referenced.
    haystack = "\n".join(corpus.values())

    unused = [
        t
        for t in inventory
        if t.name not in exclusions
        # The pre-filter below is only sound for pattern matching: dynamically
        # dispatched templates are used without their names appearing anywhere.
        and dynamic_dispatch_note(t) is None
        and (t.name not in haystack or find_usage(t, index) is None)
    ]

    used_exclusions: dict[str, str] = {}
    missing_exclusions: set[str] = set()
    names = {t.name for t in inventory}
    for name in exclusions:
        if name not in names:
            missing_exclusions.add(name)
            continue
        for t in (candidate for candidate in inventory if candidate.name == name):
            if evidence := find_usage(t, index):
                used_exclusions[name] = evidence

    return Analysis(
        templates=inventory,
        unused=unused,
        used_exclusions=used_exclusions,
        missing_exclusions=missing_exclusions,
    )
