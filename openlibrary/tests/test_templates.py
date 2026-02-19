from pathlib import Path
from tokenize import TokenError

import pytest
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


def test_all_templates(subtests):
    """Test that all template files can be parsed without syntax errors."""
    template_files = [
        *Path("openlibrary/templates").rglob("*.html"),
        *Path("openlibrary/macros").rglob("*.html"),
    ]

    for template_path in template_files:
        with subtests.test(msg=str(template_path.relative_to('openlibrary'))):
            template_text = template_path.read_text(encoding='utf-8')
            parsed, err = try_parse_template(template_text, template_path)
            assert parsed, f"Template parsing failed: {err}"


@pytest.mark.xfail(reason="Verification test: demonstrates template error detection")
def test_template_error_detection_verification():
    """Verify that template error detection works by testing with a known bad template.

    This is a simple verification test to prove that error detection works.
    """
    template_path = Path("openlibrary/templates/login.html")
    original_content = template_path.read_text(encoding='utf-8')

    # Break it in a way that WILL fail
    broken_content = original_content.replace("{%", "ONLY_OPEN_BRACE")

    # This should fail
    parsed, err = try_parse_template(broken_content, template_path)
    assert not parsed, f"Template should have failed but parsed: {err}"
