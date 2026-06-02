from functools import cache as functools_cache
from pathlib import Path


@functools_cache
def get_jinja_env():
    """Lazily initialize and return the Jinja2 environment (cached after first call).

    Per Jinja docs, a single Environment instance should be reused to take
    advantage of template compilation caching.
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    from openlibrary.i18n import gettext as _

    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "macros"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["_"] = _
    return env
