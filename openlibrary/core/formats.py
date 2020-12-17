"""Library for loading and dumping data to json and yaml.
"""
import json
import yaml

__all__ = [
    "load_json", "dump_json",
    "load_yaml", "dump_yaml"
]

def load_json(text):
    """Loads data from the given JSON text.
    """
    return json.loads(text)

def dump_json(data):
    return json.dumps(data)

def load_yaml(text):
    return yaml.safe_load(text)

def dump_yaml(data):
    return yaml.safe_dump(data,
        indent=4,
        allow_unicode=True,
        default_flow_style=False)

def load(text, format):
    if format == "json":
        return load_json(text)
    elif format == "yaml":
        return load_yaml(text)
    else:
        raise Exception("unsupported format %r" % format)

def dump(data, format):
    if format == "json":
        return dump_json(data)
    elif format == "yml":
        return dump_yaml(data)
    else:
        raise Exception("unsupported format %r" % format)
