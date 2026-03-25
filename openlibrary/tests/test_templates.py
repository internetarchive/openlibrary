import glob
from pathlib import Path
from tokenize import TokenError

import pytest
from web.template import Template


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
