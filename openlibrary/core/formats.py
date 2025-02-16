"""Library for loading and dumping data to json and yaml."""

import json

import yaml

from openlibrary.core.helpers import NothingEncoder

__all__ = ["dump_yaml", "load_yaml"]


def load_yaml(text):
    return yaml.safe_load(text)


def dump_yaml(data):
    return yaml.safe_dump(data, indent=4, allow_unicode=True, default_flow_style=False)


def load(text, format):
    if format == "json":
        return json.loads(text)
    elif format == "yaml":
        return load_yaml(text)
    else:
        raise Exception("unsupported format %r" % format)


def dump(data, format):
    if format == "json":
        return json.dumps(data, cls=NothingEncoder)
    elif format == "yml":
        return dump_yaml(data)
    else:
        raise Exception("unsupported format %r" % format)
