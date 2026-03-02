import pytest
import web

from infogami.utils import template
from openlibrary.core import fast_ctx


def test_fast_ctx_in_template(render_template, monkeypatch):
    """
    Test that fast_ctx works correctly when used inside a template.
    We use the Metatags macro because it calls set_share_links,
    which we've updated to use fast_ctx.
    """
    # 1. Setup
    fast_ctx.clear()
    monkeypatch.setattr(web, "ctx", web.storage())

    # Mock request.canonical_url which is used in Metatags.html
    request = web.storage(canonical_url="https://openlibrary.org/test")
    web.ctx.request = request

    # Manually inject into template globals for the test
    monkeypatch.setitem(web.template.Template.globals, "fast_ctx", fast_ctx)
    monkeypatch.setitem(web.template.Template.globals, "request", request)

    # Manually load macros directory into disktemplates
    template.disktemplates.load_templates("openlibrary/macros")

    # 2. Render a template that uses set_share_links
    # Metatags(title, image, description)
    render_template("Metatags", title="Test Title", image="https://openlibrary.org/image.png", description="Test Description")

    # 3. Verify
    # The template should have called set_share_links(url=..., title=...)
    # which sets fast_ctx.share_links
    assert hasattr(fast_ctx, "share_links")
    assert len(fast_ctx.share_links) == 3
    assert fast_ctx.share_links[0]["text"] == "Facebook"
    assert "Test+Title" in fast_ctx.share_links[1]["url"]  # Twitter link has title


def test_fast_ctx_get_set_in_template(render_template, monkeypatch):
    """
    Test manual get/set of fast_ctx within a template.
    """
    fast_ctx.clear()
    monkeypatch.setattr(web, "ctx", web.storage())
    monkeypatch.setitem(web.template.Template.globals, "fast_ctx", fast_ctx)

    t_code = """$def with ()
$ fast_ctx['foo'] = "bar"
<p>$fast_ctx.get('foo')</p>
"""
    import os

    # Create a temporary directory for our test template
    test_dir = "openlibrary/templates/tmp_test"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    test_template_path = os.path.join(test_dir, "test_fast_ctx.html")
    with open(test_template_path, "w") as f:
        f.write(t_code)

    try:
        # Load the temporary directory
        template.disktemplates.load_templates(test_dir)
        html = render_template("test_fast_ctx")
        assert "bar" in html
        assert fast_ctx.foo == "bar"
    finally:
        if os.path.exists(test_template_path):
            os.remove(test_template_path)
        if os.path.exists(test_dir):
            os.rmdir(test_dir)


def test_fast_ctx_fallback_error_logic():
    """
    Verify fallback error logic directly.
    We've already seen fast_ctx works in templates from tests above.
    """
    fast_ctx.clear()
    web.ctx.legacy_val = "I am old"

    with pytest.raises(AttributeError, match=r"found in web.ctx with value 'I am old'"):
        fast_ctx.get("legacy_val")

    with pytest.raises(AttributeError, match=r"found in web.ctx with value 'I am old'"):
        _ = fast_ctx.legacy_val
