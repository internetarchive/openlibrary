"""Utility for loading config file."""

import os
import sys

import web
import yaml

import infogami
from infogami import config
from infogami.infobase import server as infobase_server


# TODO: Remove once infogami supports psycopg3 natively (#10258)
def _patch_infogami_for_psycopg3():
    """
    Temporary patch: wraps infogami's parse_db_parameters to preserve
    the 'driver' key, which infogami currently strips out.
    """
    orig = infobase_server.parse_db_parameters
    if getattr(orig, "_is_patched", False):
        return

    def patched(d):
        try:
            result = orig(d)
        except KeyError as e:
            # Only handle missing 'db'/'database' — let other KeyErrors propagate
            if isinstance(d, dict) and "driver" in d and e.args[0] in ("db", "database"):
                return d
            raise

        if result and isinstance(d, dict) and "driver" in d:
            result["driver"] = d["driver"]
        return result

    patched._is_patched = True
    infobase_server.parse_db_parameters = patched


_patch_infogami_for_psycopg3()


runtime_config = {}


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
    setup_infobase_config(config_file)

    # This sets web.config.db_parameters
    infobase_server.update_config(config.infobase)

    # Safety net: ensure driver survives update_config
    # TODO: Remove once infogami is updated (#10258)
    if isinstance(web.config.get("db_parameters"), dict):
        web.config.db_parameters.setdefault("driver", "psycopg")


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
