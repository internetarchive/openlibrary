import glob
import re
from pathlib import Path
from tokenize import TokenError
from typing import Literal

import pytest
from web.template import Template

from openlibrary.core.jinja import get_jinja_env


def get_template_paths(suffix: Literal[".html", ".html.jinja"]) -> list[Path]:
    """Return all templates with the given suffix under ``templates/`` and ``macros/``.

    Mirrors the directory layout used by the Templetor compile test so a
    single helper covers every place a template (Templetor or Jinja) can
    live in the project.
    """
    template_files = []
    for pattern_root in ("openlibrary/templates", "openlibrary/macros"):
        template_files += glob.glob(f"{pattern_root}/**/*{suffix}", recursive=True)
    return sorted(set(map(Path, template_files)))


def try_parse_template(template_text: str, filename: Path) -> tuple[bool, str | Exception | None]:
    try:
        Template(template_text, str(filename))
        return True, None
    except SyntaxError as e:
        return False, f"{e.args[0]} - {e.lineno}:{e.offset}"
    except TokenError as e:
        return False, e


@pytest.mark.parametrize("filename", get_template_paths(".html"), ids=str)
def test_valid_template(filename: Path):
    parsed, err = try_parse_template(filename.read_text(encoding="utf-8"), filename)
    assert parsed, err


@pytest.mark.parametrize("filename", get_template_paths(".html"), ids=str)
def test_noopener_noreferrer(filename: Path):
    content = filename.read_text(encoding="utf-8")
    # Find all anchor tags
    a_tags = re.findall(r"<a\s+([^>]+)>", content, re.IGNORECASE)
    for attrs in a_tags:
        if 'target="_blank"' in attrs or "target='_blank'" in attrs:
            assert 'rel="noopener noreferrer"' in attrs or "rel='noopener noreferrer'" in attrs, (
                f"Missing rel='noopener noreferrer' on external link in {filename}"
            )


def test_login_template_does_not_bind_password_value():
    template = Path("openlibrary/templates/login.html").read_text(encoding="utf-8")
    assert "$form.password.value" not in template


def test_no_role_trio_in_source():
    """No source file should use all three of is_admin(), is_librarian(),
    is_super_librarian() on the same line -- use is_librarian_or_higher() instead.
    """
    excluded = {"vendor", "node_modules", ".git", "__pycache__", "tests"}
    source_roots = [
        "openlibrary/plugins",
        "openlibrary/templates",
        "openlibrary/macros",
        "openlibrary/core",
        "openlibrary/fastapi",
        "openlibrary/code.py",
        "openlibrary/asgi_app.py",
    ]

    violations = {}
    for root in source_roots:
        if root.endswith(".py"):
            files = [Path(root)]
        else:
            files = glob.glob(f"{root}/**/*", recursive=True)

        for path in files:
            p = Path(path)
            if any(part in excluded for part in p.parts):
                continue
            if p.suffix not in (".py", ".html"):
                continue
            if not p.is_file():
                continue

            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "is_librarian_or_higher" in line:
                    continue
                if "is_admin" in line and "is_librarian" in line and "is_super_librarian" in line:
                    violations[f"{p}:{i}"] = line.strip()

    assert not violations, "Found lines using all three role checks. Use is_librarian_or_higher() instead:\n" + "\n".join(
        f"  {k}: {v}" for k, v in sorted(violations.items())
    )


def test_all_jinja_templates_compile(subtests):
    """Every ``.html.jinja`` template in the project should compile.

    Uses pytest 9's built-in ``subtests`` fixture so a single broken template
    doesn't mask failures in the rest of the templates — every template is
    compiled and reported independently.
    """

    env = get_jinja_env()
    template_paths = get_template_paths(".html.jinja")
    assert template_paths, "Expected to find at least one .html.jinja template"

    for path in template_paths:
        with subtests.test(template=str(path)):
            # ``env.parse`` runs the same compilation path as the loader
            # but doesn't require the file to be under the loader's search
            # path, which lets us cover both ``templates/`` and ``macros/``.
            env.parse(path.read_text(encoding="utf-8"))
