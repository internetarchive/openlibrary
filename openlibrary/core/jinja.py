from functools import cache as functools_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


@functools_cache
def get_jinja_env() -> Environment:
    """Lazily initialize and return the Jinja2 environment (cached after first call).

    Per Jinja docs, a single Environment instance should be reused to take
    advantage of template compilation caching.
    """
    from openlibrary.i18n import gettext as _

    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "macros"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Note on ``env.globals``:
    # Only register a callable here when it is used by roughly 10 or more
    # templates. For one-off helpers, pass the function as a keyword argument
    # to ``template.render(...)`` at the call site instead. This keeps the
    # shared env's surface area small and makes template dependencies
    # explicit and easy to grep for at the render call.
    env.globals["_"] = _
    return env
