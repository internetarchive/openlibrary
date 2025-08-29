import pytest

def render_checkbox(name, checked=False):
    """Simple helper that mimics the checkbox HTML you added."""
    if checked:
        return f'<input type="checkbox" name="{name}" checked>'
    return f'<input type="checkbox" name="{name}">'


def test_checkbox_renders_unchecked():
    html = render_checkbox("ia_newsletter")
    assert 'type="checkbox"' in html
    assert 'name="ia_newsletter"' in html
    assert "checked" not in html


def test_checkbox_renders_checked():
    html = render_checkbox("pd_request", checked=True)
    assert 'type="checkbox"' in html
    assert 'name="pd_request"' in html
    assert "checked" in html
