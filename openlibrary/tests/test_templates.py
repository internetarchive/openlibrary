import glob
from pathlib import Path
from tokenize import TokenError

import pytest
from web.template import Template

from openlibrary.core.jinja import get_jinja_env


def get_template_filenames():
    """
    Returns a list of template filenames that are valid and can be parsed.
    """

    template_files = glob.glob("openlibrary/templates/**/*.html", recursive=True)
    template_files += glob.glob("openlibrary/macros/**/*.html", recursive=True)
    return map(Path, template_files)


def try_parse_template(template_text: str, filename: Path) -> tuple[bool, str | Exception | None]:
    try:
        Template(template_text, str(filename))
        return True, None
    except SyntaxError as e:
        return False, f"{e.args[0]} - {e.lineno}:{e.offset}"
    except TokenError as e:
        return False, e


@pytest.mark.parametrize("filename", get_template_filenames(), ids=str)
def test_valid_template(filename: Path):
    parsed, err = try_parse_template(filename.read_text(encoding="utf-8"), filename)
    assert parsed, err


import re


@pytest.mark.parametrize("filename", get_template_filenames(), ids=str)
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


def get_jinja_template_paths() -> list[Path]:
    """Return all ``*.html.jinja`` templates under ``templates/`` and ``macros/``.

    Mirrors the directory layout used by the Templetor compile test so a
    single helper covers every place a Jinja template can live in the
    project.
    """
    template_files = glob.glob("openlibrary/templates/**/*.html.jinja", recursive=True)
    template_files += glob.glob("openlibrary/macros/**/*.html.jinja", recursive=True)
    return sorted(set(map(Path, template_files)))


def test_all_jinja_templates_compile(subtests):
    """Every ``.html.jinja`` template in the project should compile.

    Uses pytest 9's built-in ``subtests`` fixture so a single broken template
    doesn't mask failures in the rest of the templates — every template is
    compiled and reported independently.
    """

    env = get_jinja_env()
    template_paths = get_jinja_template_paths()
    assert template_paths, "Expected to find at least one .html.jinja template"

    for path in template_paths:
        with subtests.test(template=str(path)):
            # ``env.parse`` runs the same compilation path as the loader
            # but doesn't require the file to be under the loader's search
            # path, which lets us cover both ``templates/`` and ``macros/``.
            env.parse(path.read_text(encoding="utf-8"))
