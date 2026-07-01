from functools import cache as functools_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def render_jinja_template(template_name: str, **kwargs: Any) -> str:
    """Render a Jinja template and return the resulting HTML string.

    This is a generic helper to render any Jinja template from the macros
    directory and pass it values from Templetor templates.

    Usage in Templetor template:
        $:render_template("MyTemplate.html.jinja", foo="bar")
    """
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)


@functools_cache
def get_jinja_env() -> Environment:
    """Lazily initialize and return the Jinja2 environment (cached after first call).

    Per Jinja docs, a single Environment instance should be reused to take
    advantage of template compilation caching.
    """

    def _jinja_gettext(message: str) -> str:
        """Gettext callable for Jinja's ``install_gettext_callables``.

        Translates ``message`` using the current request's locale, then returns
        the translated string.  Jinja handles ``%(name)s``-style formatting
        separately when ``newstyle=True``, so this function only does the
        lookup — no ``%`` formatting.

        Imports are kept inside the closure so that monkeypatching in tests
        picks up the patched ``load_translations`` at render time.
        """
        from openlibrary.i18n import load_translations
        from openlibrary.utils.request_context import req_context

        translations = load_translations(req_context.get().lang)
        return translations.ugettext(message) if translations else message

    def _jinja_ngettext(singular: str, plural: str, n: int) -> str:
        """Ngettext callable for Jinja's ``install_gettext_callables``."""
        from openlibrary.i18n import load_translations
        from openlibrary.utils.request_context import req_context

        if translations := load_translations(req_context.get().lang):
            return translations.ungettext(singular, plural, n)
        return singular if n == 1 else plural

    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "macros"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=["jinja2.ext.i18n"],
    )
    env.install_gettext_callables(
        _jinja_gettext,
        _jinja_ngettext,
        newstyle=True,
    )
    env.policies["ext.i18n.trimmed"] = True
    # Note on ``env.globals``:
    # Only register a callable here when it is used by roughly 10 or more
    # templates. For one-off helpers, pass the function as a keyword argument
    # to ``template.render(...)`` at the call site instead. This keeps the
    # shared env's surface area small and makes template dependencies
    # explicit and easy to grep for at the render call.
    #
    # ``install_gettext_callables`` auto-registers ``_``, ``gettext``, and
    # ``ngettext`` in ``env.globals`` — no manual globals registration needed.
    return env
