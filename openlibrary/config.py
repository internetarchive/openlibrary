"""Utility for loading config file."""

import logging
import os
import sys
from typing import Any

import web
import yaml

import infogami
from infogami import config
from infogami.infobase import server

runtime_config: dict[str, Any] = {}

logger = logging.getLogger(__name__)


def load(config_file):
    """legacy function to load openlibary config.

    The loaded config will be available via runtime_config var in this module.
    This doesn't affect the global config.

    WARNING: This function is deprecated, please use load_config instead.
    """
    if "pytest" in sys.modules:
        # During pytest ensure we're not using like olsystem or something
        assert config_file == "conf/openlibrary.yml"
    # for historic reasons
    global runtime_config
    with open(config_file) as in_file:
        runtime_config = yaml.safe_load(in_file)


def load_config(config_file):
    """Loads the config file.

    The loaded config will be available via infogami.config.
    """
    if "pytest" in sys.modules:
        # During pytest ensure we're not using like olsystem or something
        assert config_file == "conf/openlibrary.yml"
    infogami.load_config(config_file)
    _apply_infobase_server_override()
    setup_infobase_config(config_file)

    # infogami.load_config() forwards smtp_server to web.config but not
    # smtp_port, so web.sendmail() can't be routed to a non-default SMTP
    # port (e.g. mailpit in local dev).
    if config.get("smtp_port"):
        web.config.smtp_port = config.smtp_port

    # This sets web.config.db_parameters
    server.update_config(config.infobase)


def _apply_infobase_server_override():
    """Overrides infobase_server when INFOBASE_SERVER_OVERRIDE is set.

    Containers on ol-home0 (cron-jobs, solr-updater, import-bot,
    affiliate-server) must reach Infobase via the local docker-compose
    service name rather than the shared `ol-home:7000` value in
    olsystem/etc/openlibrary.yml -- otherwise the request bounces out to
    ol-home's proxy and back, looping on the host it started from.
    compose.production.yaml sets INFOBASE_SERVER_OVERRIDE=infobase:7000
    for exactly those services; every other host leaves it unset. See #5143.
    """
    override = os.environ.get("INFOBASE_SERVER_OVERRIDE")
    if config.get("infobase_server") and override:
        logger.info(
            "INFOBASE_SERVER_OVERRIDE set; overriding infobase_server %r -> %r",
            config.infobase_server,
            override,
        )
        config.infobase_server = override


def setup_infobase_config(config_file):
    """Reads the infobase config file and assign it to config.infobase.
    The config_file is used as base to resolve relative path, if specified in the config.
    """
    if config.get("infobase_config_file"):
        dir = os.path.dirname(config_file)
        path = os.path.join(dir, config.infobase_config_file)
        with open(path) as in_file:
            config.infobase = yaml.safe_load(in_file)
    else:
        config.infobase = {}
