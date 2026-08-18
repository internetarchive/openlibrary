"""Find templates and macros that are never referenced.

Two template systems coexist:
* Templetor (Infogami): ``.html`` files under ``openlibrary/templates/`` and
  ``openlibrary/macros/``, referenced by root-relative name
  (``render_template("account/mybooks")``) or bare macro name (``CoverImage``).
* Jinja: ``*.html.jinja`` files by full path; ``{% macro %}`` defs are matched
  by call/import sites.

Every git-tracked source file is scanned; anything unreferenced is reported.
The analysis errs conservative (a missed unused template beats a false
positive).  Runtime name construction is covered by DYNAMIC_DISPATCH_RULES;
database-only usage by the exclusion lists in the test file.
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

# Source files that may contain references.  Docs (*.md) are excluded (a
# template mentioned in docs is not used by it); test files are included (a
# template rendered only from a test is still alive).
CORPUS_SUFFIXES = frozenset({".py", ".js", ".ts", ".tsx", ".vue", ".html", ".jinja", ".yml", ".yaml", ".json"})

# Never scanned: this module and its test mention template names verbatim, and
# package-lock.json dependency names could rescue a template by coincidence.
CORPUS_SKIP_FILES = frozenset(
    {
        "openlibrary/utils/template_usage.py",
        "openlibrary/tests/test_unused_templates.py",
        "package-lock.json",
    }
)

# Directories resolved by runtime name construction, never literal call sites.
# Each rule cites the dispatching code so it can be audited.
DYNAMIC_DISPATCH_RULES: dict[str, str] = {
    "type/": "infogami typetemplate(), keys from DB (infogami/utils/template.py)",
    "recentchanges/": "changeset kinds (plugins/upstream/recentchanges.py)",
    "book_providers/": "provider registry (openlibrary/book_providers.py)",
    "design/": "Jinja dynamic imports + component registry (plugins/openlibrary/design.py)",
}

JINJA_MACRO_DEF_RE = re.compile(r"{%-?\s*macro\s+(\w+)\s*\(")


@dataclass(frozen=True)
class Template:
    """A template file, or a single ``{% macro %}`` definition in one."""

    name: str
    path: Path
    kind: str

    @property
    def relpath(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()

    @property
    def rel_to_root(self) -> str:
        """Path relative to its template root (macros/ or templates/)."""
        return next(self.path.relative_to(root).as_posix() for root in TEMPLATE_ROOTS if self.path.is_relative_to(root))


@dataclass
class Analysis:
    """Result of the unused-template scan, plus the exclusion audit."""

    templates: list[Template]
    unused: list[Template]
    # Exclusion entries referenced in code (the entry hides real usage and
    # must be removed), mapped to the evidence.
    used_exclusions: dict[str, str]
    # Exclusion entries matching no template/macro on disk.
    missing_exclusions: set[str]


def build_inventory() -> list[Template]:
    """Every template file plus each ``{% macro %}`` definition under the roots."""
    templates: list[Template] = []
    for root in TEMPLATE_ROOTS:
        is_macros_root = root.name == "macros"
        for path in sorted(root.rglob("*.html")):
            # Templetor resolves names with any extension stripped: the
            # canonical name is the root-relative path minus ".html".
            name = path.relative_to(root).as_posix().removesuffix(".html")
            kind = KIND_TEMPLETOR_MACRO if is_macros_root else KIND_TEMPLETOR_TEMPLATE
            templates.append(Template(name, path, kind))
        for path in sorted(root.rglob("*.html.jinja")):
            # Jinja resolves the full root-relative path.
            templates.append(Template(path.relative_to(root).as_posix(), path, KIND_JINJA_TEMPLATE))
    for t in list(templates):  # snapshot: jinja macros are appended below
        if t.kind != KIND_JINJA_TEMPLATE:
            continue
        for match in JINJA_MACRO_DEF_RE.finditer(t.path.read_text(encoding="utf-8", errors="replace")):
            templates.append(Template(match.group(1), t.path, KIND_JINJA_MACRO))
    return sorted(set(templates), key=lambda t: (t.kind, t.relpath, t.name))


def build_corpus() -> dict[str, str]:
    """Read every git-tracked source file (hermetic: untracked scratch files
    can't change the verdict).  ``--recurse-submodules`` is load-bearing --
    references like ``render.viewpage`` live in vendor/infogami (make git).
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
    """Pre-extracted references from one corpus file, for O(1) usage checks."""

    # String literals, raw + extension-stripped: render_template() strips
    # extensions at resolve time ("site/head.tmpl" references site/head).
    quoted: frozenset[str]
    # Word tokens: Templetor macros are referenced by bare name everywhere
    # ($:macros.X, render_macro("X"), CacheableMacro("X"), JS components).
    words: frozenset[str]
    # Attributes accessed on render (render.notfound(...)): root-level
    # Templetor templates.
    render_attrs: frozenset[str]
    # Words followed by "(" and words on import lines: how Jinja macros are
    # called/imported (alias.name(...), {% from ... %}).  Only .jinja files.
    called_words: frozenset[str]
    import_words: frozenset[str]


@dataclass(frozen=True)
class SearchIndex:
    """Per-file indexes, sorted by path for stable evidence reporting."""

    entries: tuple[tuple[str, FileIndex], ...]


def _add_quoted(text: str, quoted: set[str]) -> None:
    """Add every quoted literal in text (raw + extension-stripped), recursing
    into literals that contain the other quote type ("a'b'c" nests).
    """
    for match in QUOTED_LITERAL_RE.finditer(text):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        quoted.add(literal)
        if "." in literal:
            quoted.add(literal.rsplit(".", 1)[0])
        if "'" in literal or '"' in literal:
            _add_quoted(literal, quoted)


def _index_file(text: str, suffix: str) -> FileIndex:
    is_jinja = suffix == ".jinja"
    if is_jinja:
        # Mask macro-definition names: a {% macro foo %} line is not a use of
        # foo; real calls elsewhere in the file still count.
        text = JINJA_MACRO_DEF_RE.sub(lambda m: m.group(0).replace(m.group(1), " " * len(m.group(1))), text)
    quoted: set[str] = set()
    _add_quoted(text, quoted)
    called_words: frozenset[str] = frozenset()
    import_words: frozenset[str] = frozenset()
    if is_jinja:
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


def dynamic_dispatch_note(template: Template) -> str | None:
    """Why a template is reachable with no literal call site, if so."""
    rel_to_root = template.rel_to_root
    if template.kind == KIND_JINJA_MACRO:
        if rel_to_root.startswith(tuple(DYNAMIC_DISPATCH_RULES)):
            # Imported under dynamic aliases (page.nav()), visible to no pattern.
            return "defined in a dynamically imported template"
        return None
    for prefix, why in DYNAMIC_DISPATCH_RULES.items():
        if rel_to_root.startswith(prefix):
            return f"dynamically dispatched ({why})"
    return None


def _reference_sets(template: Template, file_index: FileIndex) -> tuple[frozenset[str], ...]:
    """Token sets of ``file_index`` that can reference ``template``."""
    if template.kind == KIND_TEMPLETOR_TEMPLATE:
        # Root-level templates are also reachable as render.name(...) on
        # infogami's Render DictPile.
        if "/" not in template.name:
            return file_index.quoted, file_index.render_attrs
        return (file_index.quoted,)
    if template.kind == KIND_TEMPLETOR_MACRO:
        return (file_index.words,)
    if template.kind == KIND_JINJA_TEMPLATE:
        return (file_index.quoted,)
    # Jinja macros: calls (name(...)) and import lines.
    return file_index.called_words, file_index.import_words


def find_usage(template: Template, index: SearchIndex) -> str | None:
    """Return evidence (a corpus path or dispatch note) that this is used."""
    if note := dynamic_dispatch_note(template):
        return note

    self_rel = template.relpath
    for rel, file_index in index.entries:
        # A file's own contents never count as a reference -- except for
        # Jinja macros, whose own file counts via def-masked call sites.
        if rel == self_rel and template.kind != KIND_JINJA_MACRO:
            continue
        if any(template.name in tokens for tokens in _reference_sets(template, file_index)):
            return rel
    return None


def analyze(exclusions: Iterable[str] = ()) -> Analysis:
    """Scan the code base and report unused templates/macros.

    ``exclusions`` are names used only from database content; they are skipped
    and audited so stale entries (referenced in code, or matching nothing on
    disk) surface as errors.
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
