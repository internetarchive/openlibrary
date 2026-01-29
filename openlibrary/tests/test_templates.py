from pathlib import Path
from tokenize import TokenError

from web.template import Template


def try_parse_template(
    template_text: str, filename: Path
) -> tuple[bool, str | Exception | None]:
    try:
        Template(template_text, str(filename))
        return True, None
    except SyntaxError as e:
        return False, f"{e.args[0]} - {e.lineno}:{e.offset}"
    except TokenError as e:
        return False, e


def test_all_templates_with_subtests(subtests):
    """Test that all template files can be parsed without syntax errors.

    This uses pytest 9.0's subtests feature to test all templates in a single test.
    Benefits over parametrize:
    - Reports ALL syntax errors in one run (doesn't stop at first failure)
    - Cleaner test output (not 100+ separate test cases)
    - Easier to identify which templates have issues
    - Faster to run
    """

    template_files = [
        *Path("openlibrary/templates").rglob("*.html"),
        *Path("openlibrary/macros").rglob("*.html"),
    ]

    for template_path in template_files:
        with subtests.test(msg=str(template_path.relative_to('openlibrary'))):
            template_text = template_path.read_text(encoding='utf-8')
            parsed, err = try_parse_template(template_text, template_path)
            assert parsed, f"Template parsing failed: {err}"
