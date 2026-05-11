from pathlib import Path

import web

import infogami
from openlibrary.config import load_config
from openlibrary.utils.request_context import create_context_for_script, req_context, site


def setup_for_script(config_path: str | None = None):
    """
    Sets up the context for scripts to run.

    This is needed because scripts run in a different context than the web application.
    """
    if config_path and not Path(config_path).exists():
        raise FileNotFoundError(f"no config file at {config_path}")
    if config_path:
        load_config(config_path)
    infogami._setup()
    site.set(web.ctx.site)
    req_context.set(create_context_for_script())
