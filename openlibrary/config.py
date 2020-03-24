"""Utility for loading config file.
"""
import os
import yaml
import infogami
from infogami import config
from infogami.infobase import server

runtime_config = {}

def load(config_file):
    """legacy function to load openlibary config.

    The loaded config will be available via runtime_config var in this module.
    This doesn't affect the global config.

    WARNING: This function is deprecated, please use load_config instead.
    """
    # for historic reasons
    global runtime_config
    runtime_config = yaml.load(open(config_file))


def load_config(config_file):
    """Loads the config file.

    The loaded config will be available via infogami.config.
    """
    infogami.load_config(config_file)
    setup_infobase_config(config_file)

    # This sets web.config.db_parameters
    server.update_config(config.infobase)

def setup_infobase_config(config_file):
    """Reads the infoabse config file and assign it to config.infobase.
    The config_file is used as base to resolve relative path, if specified in the config.
    """
    if config.get("infobase_config_file"):
        dir = os.path.dirname(config_file)
        path = os.path.join(dir, config.infobase_config_file)
        config.infobase = yaml.safe_load(open(path).read())
    else:
        config.infobase = {}
