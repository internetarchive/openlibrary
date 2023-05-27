"""
For processing Tags
"""

import json

from infogami.utils.view import public

@public
def process_plugins_data(data):
    plugin_type = list(data.keys())[0]
    # Split the string into key-value pairs
    parameters = data[plugin_type].split(',')

    # Create a dictionary to store the formatted parameters
    plugin_data = {}

    # Iterate through the pairs and extract the key-value information
    for pair in parameters:
        key, value = pair.split('=')
        key = key.strip()
        plugin_data[key] = eval(value)

    return plugin_type, plugin_data